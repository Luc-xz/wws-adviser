"""Identity 领域纯函数测试。"""

from wws_adviser.modules.identity import domain


def test_password_hash_roundtrip():
    h = domain.hash_password("s3cret-Pass")
    assert h != "s3cret-Pass"
    assert domain.verify_password("s3cret-Pass", h) is True
    assert domain.verify_password("wrong", h) is False


def test_session_token_unique_and_hash_stable():
    t1 = domain.generate_session_token()
    t2 = domain.generate_session_token()
    assert t1 != t2
    assert domain.hash_token(t1) == domain.hash_token(t1)
    assert domain.hash_token(t1) != domain.hash_token(t2)


def test_hash_user_id_stable():
    uid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
    assert domain.hash_user_id(uid) == domain.hash_user_id(uid)
    assert len(domain.hash_user_id(uid)) == 32
