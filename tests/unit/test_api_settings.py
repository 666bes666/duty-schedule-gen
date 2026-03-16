from __future__ import annotations

from duty_schedule.api.settings import ApiSettings


class TestApiSettings:
    def test_defaults(self) -> None:
        s = ApiSettings(keys="", rate_limit="60/minute", auth_enabled=True)
        assert s.auth_enabled is True
        assert s.parsed_keys == []
        assert s.rate_limit_max == 60
        assert s.rate_limit_window == 60

    def test_parsed_keys(self) -> None:
        s = ApiSettings(keys="key1, key2 , key3")
        assert s.parsed_keys == ["key1", "key2", "key3"]

    def test_empty_keys(self) -> None:
        s = ApiSettings(keys="")
        assert s.parsed_keys == []

    def test_rate_limit_per_second(self) -> None:
        s = ApiSettings(rate_limit="10/second")
        assert s.rate_limit_max == 10
        assert s.rate_limit_window == 1

    def test_rate_limit_per_hour(self) -> None:
        s = ApiSettings(rate_limit="1000/hour")
        assert s.rate_limit_max == 1000
        assert s.rate_limit_window == 3600

    def test_rate_limit_invalid_falls_back(self) -> None:
        s = ApiSettings(rate_limit="bad")
        assert s.rate_limit_max == 60
        assert s.rate_limit_window == 60

    def test_auth_disabled(self) -> None:
        s = ApiSettings(auth_enabled=False)
        assert s.auth_enabled is False
