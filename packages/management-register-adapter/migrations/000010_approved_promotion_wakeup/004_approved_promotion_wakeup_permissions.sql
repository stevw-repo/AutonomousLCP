GRANT EXECUTE ON OBJECT::promotion.claim_next_approved_promotion_v1
    TO asklegal_promotion_role;
GRANT EXECUTE ON OBJECT::promotion.acknowledge_approved_promotion_started_v1
    TO asklegal_promotion_role;
DENY EXECUTE ON OBJECT::promotion.claim_next_approved_promotion_v1 TO asklegal_control_role;
DENY EXECUTE ON OBJECT::promotion.claim_next_approved_promotion_v1 TO asklegal_review_role;
DENY EXECUTE ON OBJECT::promotion.claim_next_approved_promotion_v1 TO asklegal_acquisition_role;
DENY EXECUTE ON OBJECT::promotion.claim_next_approved_promotion_v1
    TO asklegal_legal_processing_role;
DENY EXECUTE ON OBJECT::promotion.acknowledge_approved_promotion_started_v1
    TO asklegal_control_role;
DENY EXECUTE ON OBJECT::promotion.acknowledge_approved_promotion_started_v1
    TO asklegal_review_role;
DENY EXECUTE ON OBJECT::promotion.acknowledge_approved_promotion_started_v1
    TO asklegal_acquisition_role;
DENY EXECUTE ON OBJECT::promotion.acknowledge_approved_promotion_started_v1
    TO asklegal_legal_processing_role;
