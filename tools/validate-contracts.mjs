#!/usr/bin/env node

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const scriptPath = fileURLToPath(import.meta.url);
const repoRoot = path.resolve(path.dirname(scriptPath), "..");
const contractsRoot = path.join(repoRoot, "contracts");
const failures = [];

function fail(message) {
  failures.push(message);
}

function assert(condition, message) {
  if (!condition) fail(message);
}

function readBytes(relativePath) {
  return fs.readFileSync(path.join(contractsRoot, relativePath));
}

function listFiles(root, relative = "") {
  const absolute = path.join(root, relative);
  const entries = fs.readdirSync(absolute, { withFileTypes: true })
    .sort((a, b) => a.name.localeCompare(b.name, "en"));
  const files = [];
  for (const entry of entries) {
    const child = relative ? `${relative}/${entry.name}` : entry.name;
    if (entry.isSymbolicLink()) {
      throw new Error(`Symlink is forbidden in package: ${child}`);
    }
    if (entry.isDirectory()) files.push(...listFiles(root, child));
    else if (entry.isFile()) files.push(child);
    else throw new Error(`Unsupported package member: ${child}`);
  }
  return files;
}

function sha256(bytes) {
  return `sha256:${crypto.createHash("sha256").update(bytes).digest("hex")}`;
}

function rejectInvalidUnicode(value, location = "$") {
  if (typeof value === "string") {
    for (let index = 0; index < value.length; index += 1) {
      const code = value.charCodeAt(index);
      if (code >= 0xd800 && code <= 0xdbff) {
        const next = value.charCodeAt(index + 1);
        if (!(next >= 0xdc00 && next <= 0xdfff)) {
          throw new Error(`Unpaired high surrogate at ${location}`);
        }
        index += 1;
      } else if (code >= 0xdc00 && code <= 0xdfff) {
        throw new Error(`Unpaired low surrogate at ${location}`);
      }
    }
  } else if (Array.isArray(value)) {
    value.forEach((item, index) => rejectInvalidUnicode(item, `${location}[${index}]`));
  } else if (value && typeof value === "object") {
    for (const [key, item] of Object.entries(value)) {
      rejectInvalidUnicode(key, `${location}.<key>`);
      rejectInvalidUnicode(item, `${location}.${key}`);
    }
  }
}

function parseStrictJson(text, source = "JSON") {
  if (text.charCodeAt(0) === 0xfeff) throw new Error(`${source}: byte-order mark is forbidden`);
  let position = 0;

  function skipWhitespace() {
    while (position < text.length && /[\x20\x09\x0a\x0d]/.test(text[position])) position += 1;
  }

  function parseString() {
    const start = position;
    position += 1;
    let escaped = false;
    while (position < text.length) {
      const char = text[position];
      if (!escaped && char === '"') {
        position += 1;
        const raw = text.slice(start, position);
        const value = JSON.parse(raw);
        rejectInvalidUnicode(value, source);
        return value;
      }
      if (!escaped && char.charCodeAt(0) < 0x20) throw new Error(`${source}: raw control character in string`);
      if (!escaped && char === "\\") escaped = true;
      else escaped = false;
      position += 1;
    }
    throw new Error(`${source}: unterminated string`);
  }

  function parseNumber() {
    const match = text.slice(position).match(/^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?/);
    if (!match) throw new Error(`${source}: invalid number at byte ${position}`);
    position += match[0].length;
    const value = Number(match[0]);
    if (!Number.isFinite(value)) throw new Error(`${source}: non-finite number is forbidden`);
    if (Object.is(value, -0)) throw new Error(`${source}: negative zero is forbidden`);
    if (!Number.isSafeInteger(value)) throw new Error(`${source}: contracts permit safe integers only`);
    return value;
  }

  function parseArray() {
    position += 1;
    const result = [];
    skipWhitespace();
    if (text[position] === "]") {
      position += 1;
      return result;
    }
    while (true) {
      result.push(parseValue());
      skipWhitespace();
      if (text[position] === "]") {
        position += 1;
        return result;
      }
      if (text[position] !== ",") throw new Error(`${source}: expected comma in array at byte ${position}`);
      position += 1;
      skipWhitespace();
    }
  }

  function parseObject() {
    position += 1;
    const result = {};
    const keys = new Set();
    skipWhitespace();
    if (text[position] === "}") {
      position += 1;
      return result;
    }
    while (true) {
      if (text[position] !== '"') throw new Error(`${source}: expected object key at byte ${position}`);
      const key = parseString();
      if (keys.has(key)) throw new Error(`${source}: duplicate object key ${JSON.stringify(key)}`);
      keys.add(key);
      skipWhitespace();
      if (text[position] !== ":") throw new Error(`${source}: expected colon at byte ${position}`);
      position += 1;
      skipWhitespace();
      result[key] = parseValue();
      skipWhitespace();
      if (text[position] === "}") {
        position += 1;
        return result;
      }
      if (text[position] !== ",") throw new Error(`${source}: expected comma in object at byte ${position}`);
      position += 1;
      skipWhitespace();
    }
  }

  function parseValue() {
    skipWhitespace();
    const char = text[position];
    if (char === '"') return parseString();
    if (char === "{") return parseObject();
    if (char === "[") return parseArray();
    if (text.startsWith("true", position)) {
      position += 4;
      return true;
    }
    if (text.startsWith("false", position)) {
      position += 5;
      return false;
    }
    if (text.startsWith("null", position)) {
      position += 4;
      return null;
    }
    if (char === "-" || /[0-9]/.test(char ?? "")) return parseNumber();
    throw new Error(`${source}: unexpected token at byte ${position}`);
  }

  const result = parseValue();
  skipWhitespace();
  if (position !== text.length) throw new Error(`${source}: trailing content at byte ${position}`);
  rejectInvalidUnicode(result, source);
  return result;
}

function loadJson(relativePath) {
  return parseStrictJson(readBytes(relativePath).toString("utf8"), relativePath);
}

function canonicalize(value) {
  rejectInvalidUnicode(value);
  if (value === null || typeof value === "boolean" || typeof value === "string") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value) || Object.is(value, -0) || !Number.isSafeInteger(value)) {
      throw new Error("JCS contract value must be a finite non-negative-zero safe integer");
    }
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalize).join(",")}]`;
  if (value && typeof value === "object") {
    const keys = Object.keys(value).sort();
    return `{${keys.map((key) => `${JSON.stringify(key)}:${canonicalize(value[key])}`).join(",")}}`;
  }
  throw new Error(`Unsupported JCS value type: ${typeof value}`);
}

function sameValue(left, right) {
  try {
    return canonicalize(left) === canonicalize(right);
  } catch {
    return false;
  }
}

const schemaFiles = listFiles(path.join(contractsRoot, "schemas"));
const schemas = new Map();
for (const basename of schemaFiles) {
  const relativePath = `schemas/${basename}`;
  const schema = loadJson(relativePath);
  schemas.set(relativePath, schema);
  if (typeof schema.$id === "string") schemas.set(schema.$id, schema);
}

function pointerValue(document, fragment, label) {
  if (!fragment || fragment === "#") return document;
  if (!fragment.startsWith("#/")) throw new Error(`Unsupported schema fragment in ${label}: ${fragment}`);
  let current = document;
  for (const encoded of fragment.slice(2).split("/")) {
    const key = encoded.replace(/~1/g, "/").replace(/~0/g, "~");
    if (!current || typeof current !== "object" || !(key in current)) {
      throw new Error(`Unresolved schema pointer ${fragment} in ${label}`);
    }
    current = current[key];
  }
  return current;
}

function resolveSchemaRef(reference, baseFile = "schemas/common.schema.json") {
  const hashIndex = reference.indexOf("#");
  const resource = hashIndex >= 0 ? reference.slice(0, hashIndex) : reference;
  const fragment = hashIndex >= 0 ? reference.slice(hashIndex) : "";
  let relativeFile = baseFile;
  if (resource) {
    if (resource.startsWith("https://contracts.asklegal.local/v1/")) {
      relativeFile = `schemas/${resource.slice(resource.lastIndexOf("/") + 1)}`;
    } else if (resource.startsWith("http:" ) || resource.startsWith("https:")) {
      throw new Error(`External schema reference is forbidden: ${reference}`);
    } else if (resource.startsWith("schemas/")) {
      relativeFile = path.posix.normalize(resource);
    } else {
      relativeFile = path.posix.normalize(path.posix.join(path.posix.dirname(baseFile), resource));
    }
  }
  const schema = schemas.get(relativeFile);
  if (!schema) throw new Error(`Unknown schema resource ${relativeFile} from ${reference}`);
  return { schema: pointerValue(schema, fragment, relativeFile), file: relativeFile };
}

function validDateTime(value) {
  const match = value.match(/^([0-9]{4})-(0[1-9]|1[0-2])-([0-2][0-9]|3[01])T([01][0-9]|2[0-3]):([0-5][0-9]):([0-5][0-9])(?:\.[0-9]{1,9})?Z$/);
  if (!match) return false;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return day <= days[month - 1];
}

function instanceType(value) {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  if (typeof value === "number" && Number.isInteger(value)) return "integer";
  return typeof value;
}

function validateInstance(instance, schema, baseFile, location = "$", errors = []) {
  if (!schema || typeof schema !== "object" || Array.isArray(schema)) {
    errors.push(`${location}: schema node is not an object`);
    return errors;
  }
  if (schema.$ref) {
    try {
      const resolved = resolveSchemaRef(schema.$ref, baseFile);
      validateInstance(instance, resolved.schema, resolved.file, location, errors);
    } catch (error) {
      errors.push(`${location}: ${error.message}`);
    }
  }
  if (schema.const !== undefined && !sameValue(instance, schema.const)) errors.push(`${location}: value does not match const`);
  if (schema.enum && !schema.enum.some((value) => sameValue(instance, value))) errors.push(`${location}: value is not in enum`);
  if (schema.type) {
    const actual = instanceType(instance);
    if (actual !== schema.type) {
      errors.push(`${location}: expected ${schema.type}, received ${actual}`);
      return errors;
    }
  }
  if (schema.allOf) schema.allOf.forEach((child) => validateInstance(instance, child, baseFile, location, errors));
  if (schema.anyOf) {
    const passing = schema.anyOf.filter((child) => validateInstance(instance, child, baseFile, location, []).length === 0).length;
    if (passing === 0) errors.push(`${location}: no anyOf branch matched`);
  }
  if (schema.oneOf) {
    const passing = schema.oneOf.filter((child) => validateInstance(instance, child, baseFile, location, []).length === 0).length;
    if (passing !== 1) errors.push(`${location}: expected exactly one oneOf branch, received ${passing}`);
  }
  if (schema.not && validateInstance(instance, schema.not, baseFile, location, []).length === 0) errors.push(`${location}: forbidden not schema matched`);

  if (typeof instance === "string") {
    if (schema.minLength !== undefined && [...instance].length < schema.minLength) errors.push(`${location}: string is shorter than minLength`);
    if (schema.maxLength !== undefined && [...instance].length > schema.maxLength) errors.push(`${location}: string is longer than maxLength`);
    if (schema.pattern !== undefined && !new RegExp(schema.pattern, "u").test(instance)) errors.push(`${location}: string does not match pattern`);
    if (schema.format === "date-time" && !validDateTime(instance)) errors.push(`${location}: invalid canonical UTC date-time`);
  }
  if (typeof instance === "number") {
    if (schema.minimum !== undefined && instance < schema.minimum) errors.push(`${location}: number is below minimum`);
    if (schema.maximum !== undefined && instance > schema.maximum) errors.push(`${location}: number is above maximum`);
  }
  if (Array.isArray(instance)) {
    if (schema.minItems !== undefined && instance.length < schema.minItems) errors.push(`${location}: array has fewer than minItems`);
    if (schema.maxItems !== undefined && instance.length > schema.maxItems) errors.push(`${location}: array has more than maxItems`);
    if (schema.uniqueItems) {
      const values = instance.map(canonicalize);
      if (new Set(values).size !== values.length) errors.push(`${location}: array items are not unique`);
    }
    if (schema.prefixItems) {
      schema.prefixItems.forEach((child, index) => {
        if (index < instance.length) validateInstance(instance[index], child, baseFile, `${location}[${index}]`, errors);
      });
    }
    if (schema.items && typeof schema.items === "object") {
      instance.forEach((item, index) => validateInstance(item, schema.items, baseFile, `${location}[${index}]`, errors));
    }
  }
  if (instance && typeof instance === "object" && !Array.isArray(instance)) {
    const properties = schema.properties ?? {};
    for (const required of schema.required ?? []) {
      if (!Object.hasOwn(instance, required)) errors.push(`${location}: missing required property ${required}`);
    }
    for (const [key, value] of Object.entries(instance)) {
      if (properties[key]) validateInstance(value, properties[key], baseFile, `${location}.${key}`, errors);
      else if (schema.additionalProperties === false) errors.push(`${location}: unknown property ${key}`);
      else if (schema.additionalProperties && typeof schema.additionalProperties === "object") {
        validateInstance(value, schema.additionalProperties, baseFile, `${location}.${key}`, errors);
      }
    }
  }
  return errors;
}

function validateByRef(instance, reference) {
  const resolved = resolveSchemaRef(reference);
  return validateInstance(instance, resolved.schema, resolved.file);
}

const supportedSchemaKeys = new Set([
  "$schema", "$id", "$defs", "$ref", "title", "description", "type", "additionalProperties", "required", "properties",
  "const", "enum", "pattern", "format", "minLength", "maxLength", "minimum", "maximum", "minItems", "maxItems",
  "uniqueItems", "items", "prefixItems", "allOf", "anyOf", "oneOf", "not"
]);

function lintSchemaNode(node, baseFile, location) {
  if (!node || typeof node !== "object" || Array.isArray(node)) {
    fail(`${baseFile}${location}: schema node must be an object`);
    return;
  }
  for (const key of Object.keys(node)) {
    if (!supportedSchemaKeys.has(key)) fail(`${baseFile}${location}: unsupported JSON Schema keyword ${key}`);
  }
  if (node.type === "object" && node.additionalProperties !== false) {
    fail(`${baseFile}${location}: object schemas must set additionalProperties to false`);
  }
  if (node.$ref) {
    try {
      resolveSchemaRef(node.$ref, baseFile);
    } catch (error) {
      fail(`${baseFile}${location}: ${error.message}`);
    }
  }
  for (const [key, child] of Object.entries(node.$defs ?? {})) lintSchemaNode(child, baseFile, `${location}/$defs/${key}`);
  for (const [key, child] of Object.entries(node.properties ?? {})) lintSchemaNode(child, baseFile, `${location}/properties/${key}`);
  if (node.items && typeof node.items === "object") lintSchemaNode(node.items, baseFile, `${location}/items`);
  (node.prefixItems ?? []).forEach((child, index) => lintSchemaNode(child, baseFile, `${location}/prefixItems/${index}`));
  for (const keyword of ["allOf", "anyOf", "oneOf"]) {
    (node[keyword] ?? []).forEach((child, index) => lintSchemaNode(child, baseFile, `${location}/${keyword}/${index}`));
  }
  if (node.not) lintSchemaNode(node.not, baseFile, `${location}/not`);
}

function validateSchemas() {
  for (const relativePath of schemaFiles.map((name) => `schemas/${name}`)) {
    const schema = schemas.get(relativePath);
    assert(schema.$schema === "https://json-schema.org/draft/2020-12/schema", `${relativePath}: Draft 2020-12 declaration is required`);
    assert(typeof schema.$id === "string" && schema.$id.startsWith("https://contracts.asklegal.local/v1/"), `${relativePath}: package-local immutable $id is required`);
    lintSchemaNode(schema, relativePath, "#");
  }
}

function catalogueCodes(relativePath) {
  return loadJson(relativePath).entries.map((entry) => entry.code);
}

function validateCatalogues() {
  const catalogueFiles = listFiles(path.join(contractsRoot, "catalogues")).map((name) => `catalogues/${name}`);
  const ids = new Set();
  for (const relativePath of catalogueFiles) {
    const catalogue = loadJson(relativePath);
    const errors = validateByRef(catalogue, "schemas/code-catalogue.schema.json");
    if (errors.length) fail(`${relativePath}: ${errors.join("; ")}`);
    assert(!ids.has(catalogue.catalogue_id), `${relativePath}: duplicate catalogue_id ${catalogue.catalogue_id}`);
    ids.add(catalogue.catalogue_id);
    const codes = catalogue.entries.map((entry) => entry.code);
    assert(new Set(codes).size === codes.length, `${relativePath}: duplicate code`);
    assert(sameValue(codes, [...codes].sort()), `${relativePath}: entries must be sorted by code`);
  }
  const common = schemas.get("schemas/common.schema.json").$defs;
  const mirrors = [
    ["result_code", "catalogues/result-codes.json"],
    ["reason_code", "catalogues/reason-codes.json"],
    ["failure_code", "catalogues/failure-codes.json"],
    ["review_code", "catalogues/review-codes.json"],
    ["reference", "catalogues/reference-types.json"]
  ];
  for (const [definition, cataloguePath] of mirrors) {
    const schemaValues = definition === "reference" ? common.reference.properties.ref_type.enum : common[definition].enum;
    assert(sameValue(schemaValues, catalogueCodes(cataloguePath)), `${definition} enum differs from ${cataloguePath}`);
  }
  const capabilityEnum = schemas.get("schemas/capability-domain.schema.json").$defs.capability_profile.properties.capability_codes.items.enum;
  assert(sameValue(capabilityEnum, catalogueCodes("catalogues/capability-codes.json")), "Capability schema enum differs from capability catalogue");
}

function validateStateMachines() {
  const lifecycleCodes = new Set(catalogueCodes("catalogues/lifecycle-codes.json"));
  const transitionFiles = listFiles(path.join(contractsRoot, "transitions")).map((name) => `transitions/${name}`);
  const machineIds = new Set();
  for (const relativePath of transitionFiles) {
    const machine = loadJson(relativePath);
    const errors = validateByRef(machine, "schemas/state-machine.schema.json");
    if (errors.length) fail(`${relativePath}: ${errors.join("; ")}`);
    assert(!machineIds.has(machine.machine_id), `${relativePath}: duplicate machine_id`);
    machineIds.add(machine.machine_id);
    assert(sameValue(machine.states, [...machine.states].sort()), `${relativePath}: states must be sorted`);
    const states = new Set(machine.states);
    for (const state of machine.states) assert(lifecycleCodes.has(state), `${relativePath}: unknown lifecycle state ${state}`);
    for (const state of [...machine.initial_states, ...machine.terminal_states]) assert(states.has(state), `${relativePath}: declared state ${state} absent from states`);
    const allowedKeys = new Set();
    for (const transition of machine.allowed_transitions) {
      assert(states.has(transition.from) && states.has(transition.to), `${relativePath}: transition uses unknown state`);
      const key = `${transition.from}->${transition.to}`;
      assert(!allowedKeys.has(key), `${relativePath}: duplicate allowed transition ${key}`);
      allowedKeys.add(key);
    }
    for (const forbidden of machine.explicit_high_risk_forbidden_transitions) {
      const key = `${forbidden.from}->${forbidden.to}`;
      assert(states.has(forbidden.from) && states.has(forbidden.to), `${relativePath}: forbidden transition uses unknown state`);
      assert(!allowedKeys.has(key), `${relativePath}: transition is both allowed and forbidden: ${key}`);
    }
    const reached = new Set(machine.initial_states);
    let changed = true;
    while (changed) {
      changed = false;
      for (const transition of machine.allowed_transitions) {
        if (reached.has(transition.from) && !reached.has(transition.to)) {
          reached.add(transition.to);
          changed = true;
        }
      }
    }
    for (const state of machine.states) assert(reached.has(state), `${relativePath}: unreachable state ${state}`);
    for (const terminal of machine.terminal_states) {
      assert(!machine.allowed_transitions.some((transition) => transition.from === terminal), `${relativePath}: terminal state ${terminal} has an outbound transition`);
    }
  }
}

function validateInventory() {
  const relativePath = "inventory/cross-cutting-contract-inventory.json";
  const inventory = loadJson(relativePath);
  const errors = validateByRef(inventory, "schemas/contract-inventory.schema.json");
  if (errors.length) fail(`${relativePath}: ${errors.join("; ")}`);
  const objectTypes = inventory.objects.map((entry) => entry.object_type);
  assert(new Set(objectTypes).size === objectTypes.length, `${relativePath}: duplicate object_type`);
  assert(inventory.objects.length >= 40, `${relativePath}: expected at least 40 cross-cutting object entries`);
  for (const entry of inventory.objects) {
    try {
      resolveSchemaRef(entry.schema_ref);
    } catch (error) {
      fail(`${relativePath}: ${entry.object_type} has unresolved schema_ref: ${error.message}`);
    }
    if (entry.lifecycle_machine.startsWith("transitions/")) {
      assert(fs.existsSync(path.join(contractsRoot, entry.lifecycle_machine)), `${relativePath}: ${entry.object_type} has missing lifecycle machine`);
    }
  }
  const requiredObjects = [
    "Approval", "Capability Profile", "Corpus Release", "Desired-State Inventory", "Legal Item", "Observation",
    "Promotion Manifest", "Record Traceability Lookup Revision", "Registered Source", "Release Scope",
    "Routing Configuration", "Search Record / Serving Record", "Serving State Definition", "Source Snapshot"
  ];
  for (const objectType of requiredObjects) assert(objectTypes.includes(objectType), `${relativePath}: missing required cross-cutting object ${objectType}`);
}

function validateFoundationStatus() {
  const relativePath = "foundation-status.json";
  const status = loadJson(relativePath);
  const errors = validateByRef(status, "schemas/foundation-status.schema.json");
  if (errors.length) fail(`${relativePath}: ${errors.join("; ")}`);
  const expectedCapabilities = catalogueCodes("catalogues/capability-codes.json");
  const actualCapabilities = status.capabilities.map((entry) => entry.capability_code);
  assert(sameValue(actualCapabilities, expectedCapabilities), `${relativePath}: every closed capability must appear once in sorted order`);
  assert(status.deferred_decisions.length >= 8, `${relativePath}: deferred decision inventory is incomplete`);
}

function walkValues(value, callback, location = "$") {
  callback(value, location);
  if (Array.isArray(value)) value.forEach((child, index) => walkValues(child, callback, `${location}[${index}]`));
  else if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) walkValues(child, callback, `${location}.${key}`);
  }
}

function validateIdentifiersAndFingerprints() {
  const prefixes = new Set(catalogueCodes("catalogues/identity-prefixes.json"));
  for (const relativePath of listFiles(contractsRoot).filter((name) => name.endsWith(".json"))) {
    const document = loadJson(relativePath);
    walkValues(document, (value, location) => {
      if (typeof value !== "string") return;
      if (/^[a-z][a-z0-9]{2}_[0-9a-f]{48}$/.test(value)) {
        assert(prefixes.has(value.slice(0, 3)), `${relativePath}${location}: unknown identity prefix ${value.slice(0, 3)}`);
      }
      if (value.startsWith("sha256:")) {
        assert(/^sha256:[0-9a-f]{64}$/.test(value), `${relativePath}${location}: malformed fingerprint`);
      }
    });
  }
}

function expectedFixtureResult(fixture) {
  const inputBytes = readBytes(fixture.input_path);
  if (fixture.operation === "PARSE_JSON") {
    try {
      parseStrictJson(inputBytes.toString("utf8"), fixture.input_path);
      return { result_code: "PASS", failure_codes: [], reason_codes: ["VALIDATION_COMPLETE"] };
    } catch (error) {
      if (error.message.includes("negative zero")) {
        return { result_code: "BLOCK", failure_codes: ["FAILURE_NON_CANONICAL"], reason_codes: [] };
      }
      return { result_code: "BLOCK", failure_codes: ["FAILURE_MALFORMED_JSON"], reason_codes: [] };
    }
  }
  const input = parseStrictJson(inputBytes.toString("utf8"), fixture.input_path);
  if (fixture.operation === "SCHEMA_VALIDATE") {
    const errors = validateByRef(input, fixture.schema_ref);
    return errors.length === 0
      ? { result_code: "PASS", failure_codes: [], reason_codes: ["SCHEMA_VALID", "VALIDATION_COMPLETE"] }
      : { result_code: "BLOCK", failure_codes: ["FAILURE_SCHEMA_INVALID"], reason_codes: [] };
  }
  if (fixture.operation === "TRANSITION_CHECK") {
    const machine = loadJson(fixture.state_machine_ref);
    const allowed = machine.allowed_transitions.some((transition) => transition.from === input.from && transition.to === input.to);
    return allowed
      ? { result_code: "PASS", failure_codes: [], reason_codes: ["TRANSITION_ALLOWED"] }
      : { result_code: "BLOCK", failure_codes: ["FAILURE_FORBIDDEN_TRANSITION"], reason_codes: ["TRANSITION_UNLISTED"] };
  }
  if (fixture.operation === "RETRY_CHECK") {
    const first = input.attempts[0];
    const exact = input.attempts.length > 1 && input.attempts.every((attempt) => attempt.idempotency_key === first.idempotency_key && attempt.input_fingerprint === first.input_fingerprint);
    return exact
      ? { result_code: "PASS", failure_codes: [], reason_codes: ["EXACT_REPLAY", "RETRY_INPUT_UNCHANGED"] }
      : { result_code: "BLOCK", failure_codes: ["FAILURE_RETRY_INPUT_CHANGED"], reason_codes: [] };
  }
  if (fixture.operation === "IDEMPOTENCY_CHECK") {
    const first = input.registrations[0];
    const exact = input.registrations.length > 1 && input.registrations.every((registration) => registration.object_id === first.object_id && registration.input_fingerprint === first.input_fingerprint);
    return exact
      ? { result_code: "PASS", failure_codes: [], reason_codes: ["EXACT_REPLAY"] }
      : { result_code: "BLOCK", failure_codes: ["FAILURE_ID_COLLISION"], reason_codes: [] };
  }
  if (fixture.operation === "CANONICALIZE") {
    const values = input.documents.map(canonicalize);
    if (new Set(values).size !== 1) return { result_code: "BLOCK", failure_codes: ["FAILURE_REPRODUCIBILITY"], reason_codes: [] };
    return {
      result_code: "PASS",
      failure_codes: [],
      reason_codes: ["VALIDATION_COMPLETE"],
      canonical_json: values[0],
      fingerprint: sha256(Buffer.from(values[0], "utf8"))
    };
  }
  throw new Error(`Unsupported fixture operation ${fixture.operation}`);
}

function validateFixtures() {
  const catalogue = loadJson("fixtures/catalogue.json");
  assert(catalogue.schema_id === "asklegal.cross-cutting-fixture-catalogue", "fixtures/catalogue.json: wrong schema_id");
  assert(catalogue.schema_version === "1.0.0", "fixtures/catalogue.json: wrong schema_version");
  assert(catalogue.fixture_schema_ref === "schemas/fixture.schema.json", "fixtures/catalogue.json: wrong fixture schema reference");
  const ids = catalogue.fixtures.map((entry) => entry.fixture_id);
  assert(new Set(ids).size === ids.length, "fixtures/catalogue.json: duplicate fixture ID");
  assert(sameValue(ids, [...ids].sort()), "fixtures/catalogue.json: fixtures must be sorted by ID");
  const categories = new Set();
  for (const entry of catalogue.fixtures) {
    const fixture = loadJson(entry.path);
    const errors = validateByRef(fixture, "schemas/fixture.schema.json");
    if (errors.length) fail(`${entry.path}: ${errors.join("; ")}`);
    assert(fixture.fixture_id === entry.fixture_id, `${entry.path}: fixture ID differs from catalogue`);
    categories.add(fixture.category);
    assert(fs.existsSync(path.join(contractsRoot, fixture.input_path)), `${entry.path}: missing input`);
    assert(fs.existsSync(path.join(contractsRoot, fixture.expected_path)), `${entry.path}: missing expected artifact`);
    const actual = expectedFixtureResult(fixture);
    const expected = loadJson(fixture.expected_path);
    assert(sameValue(actual, expected), `${entry.path}: actual result ${canonicalize(actual)} differs from expected ${canonicalize(expected)}`);
  }
  for (const category of ["BOUNDARY", "IDEMPOTENCY", "MALFORMED_INPUT", "NEGATIVE", "POSITIVE", "REPRODUCIBILITY", "RETRY"]) {
    assert(categories.has(category), `fixtures/catalogue.json: missing required category ${category}`);
  }
}

function mediaType(relativePath) {
  if (relativePath.endsWith(".json")) return "application/json";
  if (relativePath.endsWith(".md")) return "text/markdown";
  return "text/plain";
}

function fileRole(relativePath) {
  if (relativePath === "README.md") return "PACKAGE_DOCUMENTATION";
  if (relativePath === "foundation-status.json") return "FOUNDATION_STATUS";
  if (relativePath.startsWith("catalogues/")) return "CLOSED_CODE_CATALOGUE";
  if (relativePath.startsWith("schemas/")) return "JSON_SCHEMA";
  if (relativePath.startsWith("transitions/")) return "STATE_MACHINE";
  if (relativePath.startsWith("inventory/")) return "CONTRACT_INVENTORY";
  if (relativePath === "fixtures/catalogue.json") return "FIXTURE_CATALOGUE";
  if (relativePath.endsWith("/fixture.json")) return "FIXTURE_DECLARATION";
  if (relativePath.endsWith("/expected.json")) return "EXPECTED_ARTIFACT";
  return "SYNTHETIC_INPUT";
}

function buildManifest() {
  const files = listFiles(contractsRoot)
    .filter((relativePath) => relativePath !== "package-manifest.json")
    .map((relativePath) => {
      const bytes = readBytes(relativePath);
      return {
        path: relativePath,
        role: fileRole(relativePath),
        media_type: mediaType(relativePath),
        byte_size: bytes.length,
        fingerprint: sha256(bytes)
      };
    });
  return {
    schema_id: "asklegal.cross-cutting-package-manifest",
    schema_version: "1.0.0",
    package_id: "pkg_000000000000000000000000000000000000000000000001",
    package_version: "1.0.0",
    created_at: "2026-08-14T00:00:00Z",
    canonicalization: "RFC8785-JCS",
    fingerprint_algorithm: "SHA-256",
    manifest_exclusion: "package-manifest.json",
    files
  };
}

function validatePackageManifest() {
  const relativePath = "package-manifest.json";
  assert(fs.existsSync(path.join(contractsRoot, relativePath)), `${relativePath}: missing`);
  if (!fs.existsSync(path.join(contractsRoot, relativePath))) return;
  const manifest = loadJson(relativePath);
  const errors = validateByRef(manifest, "schemas/package-manifest.schema.json");
  if (errors.length) fail(`${relativePath}: ${errors.join("; ")}`);
  const expected = buildManifest();
  assert(sameValue(manifest, expected), `${relativePath}: exact file inventory, byte sizes, or fingerprints are stale`);
}

function validateMarkdown() {
  const markdownFiles = ["AGENTS.md", "README.md", ...listFiles(path.join(repoRoot, "docs")).filter((name) => name.endsWith(".md")).map((name) => `docs/${name}`), "contracts/README.md"];
  for (const relativePath of markdownFiles) {
    const absolute = path.join(repoRoot, relativePath);
    const text = fs.readFileSync(absolute, "utf8");
    const lines = text.split(/\r?\n/);
    let inFence = false;
    let h1Count = 0;
    for (const line of lines) {
      if (/^```/.test(line)) inFence = !inFence;
      if (!inFence && /^# /.test(line)) h1Count += 1;
    }
    assert(!inFence, `${relativePath}: unbalanced fenced code block`);
    assert(h1Count === 1, `${relativePath}: expected exactly one level-one heading, found ${h1Count}`);
    const linkPattern = /\[[^\]]*\]\(([^)]+)\)/g;
    for (const match of text.matchAll(linkPattern)) {
      let target = match[1].trim();
      if (target.startsWith("<") && target.endsWith(">")) target = target.slice(1, -1);
      if (/^(?:https?:|mailto:|#)/.test(target)) continue;
      target = target.split("#")[0];
      if (!target) continue;
      const resolved = path.resolve(path.dirname(absolute), decodeURIComponent(target));
      assert(fs.existsSync(resolved), `${relativePath}: broken local link ${target}`);
    }
  }
}

function buildSnapshot() {
  const files = listFiles(contractsRoot).sort();
  return files.map((relativePath) => {
    const bytes = readBytes(relativePath);
    const entry = { path: relativePath, exact_fingerprint: sha256(bytes) };
    if (relativePath.endsWith(".json")) {
      const value = parseStrictJson(bytes.toString("utf8"), relativePath);
      entry.canonical_fingerprint = sha256(Buffer.from(canonicalize(value), "utf8"));
    }
    return entry;
  });
}

function validateIsolatedReproducibility() {
  const first = spawnSync(process.execPath, [scriptPath, "--snapshot-only"], { cwd: repoRoot, encoding: "utf8" });
  const second = spawnSync(process.execPath, [scriptPath, "--snapshot-only"], { cwd: repoRoot, encoding: "utf8" });
  assert(first.status === 0, `First isolated snapshot failed: ${first.stderr.trim()}`);
  assert(second.status === 0, `Second isolated snapshot failed: ${second.stderr.trim()}`);
  assert(first.stdout === second.stdout, "Two isolated clean snapshots are not byte-identical");
}

if (process.argv.includes("--print-manifest")) {
  process.stdout.write(`${JSON.stringify(buildManifest(), null, 2)}\n`);
  process.exit(0);
}

if (process.argv.includes("--snapshot-only")) {
  process.stdout.write(canonicalize(buildSnapshot()));
  process.exit(0);
}

try {
  validateSchemas();
  validateCatalogues();
  validateStateMachines();
  validateInventory();
  validateFoundationStatus();
  validateIdentifiersAndFingerprints();
  validateFixtures();
  validatePackageManifest();
  validateMarkdown();
  validateIsolatedReproducibility();
} catch (error) {
  fail(`Validator crashed: ${error.stack ?? error.message}`);
}

if (failures.length) {
  console.error(`Contract validation failed with ${failures.length} issue(s):`);
  failures.forEach((message, index) => console.error(`${index + 1}. ${message}`));
  process.exit(1);
}

const manifestFingerprint = sha256(Buffer.from(canonicalize(loadJson("package-manifest.json")), "utf8"));
console.log("PASS schemas: Draft 2020-12 structure, closed objects, and local references");
console.log("PASS catalogues: closed, unique, sorted, and mirrored by schema enums");
console.log("PASS transitions: reachable closed-world states and explicit forbidden behavior");
console.log("PASS inventory: cross-cutting object ownership, schemas, identities, references, lifecycles, and invariants");
console.log("PASS fixtures: positive, negative, boundary, malformed, retry, idempotency, and reproducibility cases");
console.log("PASS package: exact contained paths, byte sizes, fingerprints, and no undeclared files");
console.log("PASS documentation: local links, level-one headings, and fenced blocks");
console.log("PASS reproducibility: two isolated byte-identical package snapshots");
console.log(`PACKAGE_MANIFEST_FINGERPRINT ${manifestFingerprint}`);
