from lib.dedup import branch_name, slugify, submission_hash


def test_slugify_basic():
    assert slugify("Fire Bolt") == "fire-bolt"
    assert slugify("FIREBOLT") == "firebolt"


def test_slugify_collapses_non_alphanumeric():
    # runs of non-alphanumeric chars collapse to a single dash
    assert slugify("Fire   Bolt!!") == "fire-bolt"
    assert slugify("a  ---  b__c") == "a-b-c"


def test_slugify_trims_leading_trailing_dashes():
    assert slugify("  Fire Bolt  ") == "fire-bolt"
    assert slugify("!!!Fireball!!!") == "fireball"


def test_slugify_caps_at_50_chars():
    assert len(slugify("x" * 200)) == 50
    # a name that slugifies to exactly 50 is unchanged in length
    assert len(slugify("a" * 50)) == 50


def test_submission_hash_is_12_hex_chars():
    h = submission_hash(1, 2, "Fire Bolt")
    assert len(h) == 12
    assert all(c in "0123456789abcdef" for c in h)


def test_submission_hash_is_deterministic():
    assert submission_hash(1, 2, "Fire Bolt") == submission_hash(1, 2, "Fire Bolt")


def test_submission_hash_normalizes_case_and_whitespace():
    # casing + surrounding whitespace are normalized away (strip().lower())
    assert submission_hash(1, 2, "  Fire Bolt ") == submission_hash(1, 2, "fire bolt")


def test_submission_hash_punctuation_is_significant():
    # only case/whitespace are normalized; punctuation still distinguishes names
    assert submission_hash(1, 2, "Fire Bolt!!") != submission_hash(1, 2, "Fire Bolt")


def test_submission_hash_disambiguates_thread_user_and_name():
    base = submission_hash(1, 2, "Fire Bolt")
    assert submission_hash(9, 2, "Fire Bolt") != base  # different thread
    assert submission_hash(1, 9, "Fire Bolt") != base  # different user
    assert submission_hash(1, 2, "Ice Bolt") != base   # different name


def test_branch_name_format():
    name = branch_name(999888777, 123123123, "Live Test Automation")
    assert name.startswith("user-automation/")
    slug, _, digest = name[len("user-automation/"):].rpartition("-")
    assert slug == "live-test-automation"
    assert len(digest) == 12


def test_branch_name_worst_case_length_within_limit():
    # user-automation/ (16) + slug (<=50) + '-' (1) + hash (12) = <=79, well under GitHub's limit
    name = branch_name(1, 2, "z" * 200)
    assert len(name) == 79
    assert len(name) <= 79


def test_branch_name_matches_dedup_key_semantics():
    # trivial resubmission differences (case/whitespace) yield the SAME branch...
    assert branch_name(1, 2, "  Fire Bolt ") == branch_name(1, 2, "fire bolt")
    # ...while a genuinely different automation in the same thread does not
    assert branch_name(1, 2, "Fire Bolt") != branch_name(1, 2, "Ice Bolt")
