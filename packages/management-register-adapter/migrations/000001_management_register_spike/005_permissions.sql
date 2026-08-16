GRANT EXECUTE ON OBJECT::register.resolve_command TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::review.consume_approval TO asklegal_review_role;
GRANT EXECUTE ON OBJECT::register.resolve_command TO asklegal_promotion_role;
GRANT EXECUTE ON OBJECT::promotion.activate_serving_state TO asklegal_promotion_role;

DENY INSERT, UPDATE, DELETE ON SCHEMA::register TO asklegal_review_role;
DENY INSERT, UPDATE, DELETE ON SCHEMA::review TO asklegal_review_role;
DENY INSERT, UPDATE, DELETE ON SCHEMA::register TO asklegal_promotion_role;
DENY INSERT, UPDATE, DELETE ON SCHEMA::promotion TO asklegal_promotion_role;
