from __future__ import annotations

import inspect
import json
import os
import re
import unittest
from unittest.mock import MagicMock, patch

from tdm_adapter import (
    HTTP_TIMEOUT_SECONDS,
    ProfileInfo,
    ProfilesByEmailResult,
    create_customer_share_a_car,
    create_reservation_guest_user,
    create_reservation_logged_in_user,
    create_user_and_reservation,
    get_profiles_by_email_address,
)

_TEST_SHARE_CAR_USER_URL = "https://example.test/ShareCarUser"
_TEST_RENTAL_RESERVATION_V2_URL = "https://example.test/RentalReservationV2"
_TEST_GET_PROFILES_BY_EMAIL_URL = (
    "https://example.test/com.sixt.service.customer_person.PersonRead/"
    "GetProfilesByEmailAddress"
)

_EXPECTED_DEFAULT_RENTAL_PAYLOAD = {
    "pickup_station": "4",
    "return_station": "4",
    "pickup_date": "@@date(+3d)",
    "return_date": "@@date(+6d)",
    "pickup_time": "0900",
    "return_time": "1700",
    "prepaid": False,
    "young_driver": False,
    "carGroup": "",
    "customer": {
        "corporate_customer_id": "",
        "profile_id": "",
        "person_id": "",
        "contact": {
            "salutation": "@@person.salutation",
            "first_name": "@@person.firstname",
            "last_name": "@@person.lastname",
            "email": "@@person.email",
            "phone_number": "@@person.phone",
        },
        "birth_date": "@@person.birthdate",
    },
    "maestro": False,
    "wholesaler_reservation": False,
}

_EXPECTED_LOGGED_IN_RENTAL_PAYLOAD = {
    **_EXPECTED_DEFAULT_RENTAL_PAYLOAD,
    "customer": {
        **_EXPECTED_DEFAULT_RENTAL_PAYLOAD["customer"],
        "profile_id": "104788471",
        "person_id": "87563910",
    },
}

_LOOKS_LIKE_EMAIL = re.compile(
    r"\A[a-zA-Z0-9][a-zA-Z0-9._%+-]*@[a-zA-Z0-9](?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?"
    r"\.[a-zA-Z]{2,}\Z"
)


class TestTDMAdapter(unittest.TestCase):
    @patch.dict(
        os.environ,
        {"TEST_PARAM_SHARE_CAR_USER_URL": _TEST_SHARE_CAR_USER_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_customer_share_a_car_returns_email(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"name": "created.user@example.com"}
        mock_post.return_value = mock_response

        result = create_customer_share_a_car()

        self.assertEqual(result, "created.user@example.com")
        self.assertRegex(result, _LOOKS_LIKE_EMAIL)
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {"userType": "SAC", "tcId": "tdm-generated"})
        self.assertEqual(_args[0], _TEST_SHARE_CAR_USER_URL)
        auth = kwargs["headers"]["Authorization"]
        self.assertEqual(auth, "Bearer test-token")
        self.assertEqual(kwargs["timeout"], HTTP_TIMEOUT_SECONDS)

    def test_create_customer_share_a_car_default_parameters(self) -> None:
        sig = inspect.signature(create_customer_share_a_car)
        self.assertEqual(sig.parameters["user_type"].default, "SAC")
        self.assertEqual(sig.parameters["test_case_id"].default, "tdm-generated")

    @patch.dict(
        os.environ,
        {"TEST_PARAM_SHARE_CAR_USER_URL": _TEST_SHARE_CAR_USER_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_customer_share_a_car_accepts_overrides(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"name": "x@y.com"}
        mock_post.return_value = mock_response

        result = create_customer_share_a_car(
            user_type="CUSTOM",
            test_case_id="case-001",
        )

        self.assertEqual(result, "x@y.com")
        self.assertRegex(result, _LOOKS_LIKE_EMAIL)
        _args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"], {"userType": "CUSTOM", "tcId": "case-001"})

    @patch.dict(
        os.environ,
        {"TEST_PARAM_SHARE_CAR_USER_URL": _TEST_SHARE_CAR_USER_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_customer_share_a_car_name_json_string_decodes(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        """API may return ``name`` as a JSON-encoded string (quoted fragment)."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"name": json.dumps("wrapped@example.net")}
        mock_post.return_value = mock_response

        result = create_customer_share_a_car()

        self.assertEqual(result, "wrapped@example.net")
        self.assertRegex(result, _LOOKS_LIKE_EMAIL)

    def test_create_customer_share_a_car_rejects_blank_user_type(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            create_customer_share_a_car(user_type="  ", test_case_id="tdm-generated")
        self.assertIn("user_type", str(ctx.exception).lower())

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_reservation_guest_user_returns_ten_digit_int(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rental_reservation_number": 5_432_109_876,
        }
        mock_post.return_value = mock_response

        result = create_reservation_guest_user()

        self.assertIsInstance(result, int)
        self.assertEqual(result, 5_432_109_876)
        self.assertEqual(len(str(result)), 10)
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        self.assertEqual(_args[0], _TEST_RENTAL_RESERVATION_V2_URL)
        self.assertEqual(kwargs["json"], _EXPECTED_DEFAULT_RENTAL_PAYLOAD)

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_reservation_guest_user_calls_auth(
        self,
        mock_token: MagicMock,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rental_reservation_number": 1_111_111_111,
        }
        mock_post.return_value = mock_response

        create_reservation_guest_user()

        mock_token.assert_called_once()
        mock_post.assert_called_once()

    def test_create_reservation_guest_user_default_parameters(self) -> None:
        sig = inspect.signature(create_reservation_guest_user)
        names = tuple(sig.parameters)
        self.assertEqual(
            names,
            (
                "pickup_station",
                "return_station",
                "pickup_date",
                "return_date",
                "prepaid",
            ),
        )
        self.assertEqual(sig.parameters["pickup_station"].default, 4)
        self.assertEqual(sig.parameters["return_station"].default, 4)
        self.assertEqual(sig.parameters["pickup_date"].default, "@@date(+3d)")
        self.assertEqual(sig.parameters["return_date"].default, "@@date(+6d)")
        self.assertIs(sig.parameters["prepaid"].default, False)

    def test_reservation_guest_user_rejects_pickup_station_over_max(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            create_reservation_guest_user(10_000_000)
        self.assertIn("pickup_station", str(ctx.exception))

    def test_create_reservation_guest_user_rejects_bool_pickup_station(self) -> None:
        with self.assertRaises(TypeError) as ctx:
            create_reservation_guest_user(True, 4)  # type: ignore[arg-type]
        self.assertIn("bool", str(ctx.exception).lower())

    def test_create_reservation_guest_user_rejects_prepaid_int(self) -> None:
        with self.assertRaises(TypeError) as ctx:
            create_reservation_guest_user(prepaid=1)  # type: ignore[arg-type]
        self.assertIn("bool", str(ctx.exception).lower())

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.get_profiles_by_email_address")
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_reservation_logged_in_user_passes_profile_and_person_id(
        self,
        _mock_token: object,
        mock_post: MagicMock,
        mock_profiles: MagicMock,
    ) -> None:
        mock_profiles.return_value = ProfilesByEmailResult(
            profiles=[
                ProfileInfo(profile_id="104788471", corporate_customer_id=""),
            ],
            person_id="87563910",
            member_id="1",
        )
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rental_reservation_number": 5_432_109_876,
        }
        mock_post.return_value = mock_response

        result = create_reservation_logged_in_user("  someone@example.com  ")

        self.assertEqual(result, 5_432_109_876)
        mock_profiles.assert_called_once_with("someone@example.com")
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        self.assertEqual(_args[0], _TEST_RENTAL_RESERVATION_V2_URL)
        self.assertEqual(kwargs["json"], _EXPECTED_LOGGED_IN_RENTAL_PAYLOAD)

    @patch("tdm_adapter.create_reservation_logged_in_user")
    @patch("tdm_adapter.create_customer_share_a_car")
    def test_create_user_and_reservation_returns_email_and_number(
        self,
        mock_share_car: MagicMock,
        mock_reservation: MagicMock,
    ) -> None:
        mock_share_car.return_value = "new.user@example.com"
        mock_reservation.return_value = 5_123_456_789

        result = create_user_and_reservation()

        self.assertEqual(result, ("new.user@example.com", 5_123_456_789))
        mock_share_car.assert_called_once_with()
        mock_reservation.assert_called_once_with("new.user@example.com")

    def test_create_user_and_reservation_has_no_parameters(self) -> None:
        sig = inspect.signature(create_user_and_reservation)
        self.assertEqual(tuple(sig.parameters), ())

    def test_create_reservation_logged_in_user_default_parameters(self) -> None:
        sig = inspect.signature(create_reservation_logged_in_user)
        names = tuple(sig.parameters)
        self.assertEqual(
            names,
            (
                "email_address",
                "pickup_station",
                "return_station",
                "pickup_date",
                "return_date",
                "prepaid",
            ),
        )
        self.assertEqual(sig.parameters["pickup_station"].default, 4)
        self.assertEqual(sig.parameters["return_station"].default, 4)
        self.assertEqual(sig.parameters["pickup_date"].default, "@@date(+3d)")
        self.assertEqual(sig.parameters["return_date"].default, "@@date(+6d)")
        self.assertIs(sig.parameters["prepaid"].default, False)

    def test_reservation_logged_in_user_rejects_pickup_station_over_max(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            create_reservation_logged_in_user("a@b.co", 10_000_000)
        self.assertIn("pickup_station", str(ctx.exception))

    def test_reservation_logged_in_user_rejects_blank_email(self) -> None:
        with self.assertRaises(AssertionError):
            create_reservation_logged_in_user("   ")

    def test_reservation_logged_in_user_rejects_non_str_email(self) -> None:
        with self.assertRaises(TypeError) as ctx:
            create_reservation_logged_in_user(None)  # type: ignore[arg-type]
        self.assertIn("email_address", str(ctx.exception))

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.get_profiles_by_email_address")
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_reservation_logged_in_user_rejects_empty_profiles_list(
        self,
        _mock_token: object,
        _mock_post: MagicMock,
        mock_profiles: MagicMock,
    ) -> None:
        mock_profiles.return_value = ProfilesByEmailResult(
            profiles=[],
            person_id="87563910",
            member_id="1",
        )
        with self.assertRaises(ValueError) as ctx:
            create_reservation_logged_in_user("nobody@example.com")
        self.assertIn("empty profiles list", str(ctx.exception))

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_reservation_guest_user_accepts_max_station_ids(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rental_reservation_number": 2_222_222_222,
        }
        mock_post.return_value = mock_response

        result = create_reservation_guest_user(9_999_999, 9_999_999)

        self.assertIsInstance(result, int)
        self.assertEqual(len(str(result)), 10)
        _args, kwargs = mock_post.call_args
        self.assertEqual(kwargs["json"]["pickup_station"], "9999999")
        self.assertEqual(kwargs["json"]["return_station"], "9999999")

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_reservation_guest_user_overrides_dates_and_prepaid(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rental_reservation_number": 3_333_333_333,
        }
        mock_post.return_value = mock_response

        create_reservation_guest_user(
            4,
            4,
            "@@date(+1d)",
            "@@date(+7d)",
            True,
        )

        _args, kwargs = mock_post.call_args
        body = kwargs["json"]
        self.assertEqual(body["pickup_date"], "@@date(+1d)")
        self.assertEqual(body["return_date"], "@@date(+7d)")
        self.assertIs(body["prepaid"], True)

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_reservation_guest_user_rental_number_json_string(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        """``rental_reservation_number`` may arrive as a JSON-encoded string."""
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "rental_reservation_number": json.dumps("6543210987"),
        }
        mock_post.return_value = mock_response

        result = create_reservation_guest_user()

        self.assertEqual(result, 6_543_210_987)

    @patch.dict(
        os.environ,
        {"TEST_PARAM_RENTAL_RESERVATION_V2_URL": _TEST_RENTAL_RESERVATION_V2_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_create_reservation_guest_user_rejects_non_ten_digit_number(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {"rental_reservation_number": "12345"}
        mock_post.return_value = mock_response

        with self.assertRaises(ValueError) as ctx:
            create_reservation_guest_user()
        self.assertIn("10 decimal digits", str(ctx.exception))

    @patch.dict(
        os.environ,
        {"TEST_PARAM_GET_PROFILES_BY_EMAIL_URL": _TEST_GET_PROFILES_BY_EMAIL_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_get_profiles_by_email_address_posts_email_and_returns_structure(
        self,
        mock_token: MagicMock,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "profiles": [
                {
                    "profile_id": "104788471",
                    "corporate_customer_id": "",
                }
            ],
            "person_id": "87563910",
            "member_id": "SXT87563910",
        }
        mock_post.return_value = mock_response

        result = get_profiles_by_email_address("  user@example.com  ")

        self.assertEqual(
            result,
            {
                "profiles": [
                    {
                        "profile_id": "104788471",
                        "corporate_customer_id": "",
                    }
                ],
                "person_id": "87563910",
                "member_id": "SXT87563910",
            },
        )
        mock_token.assert_called_once()
        mock_post.assert_called_once()
        _args, kwargs = mock_post.call_args
        self.assertEqual(_args[0], _TEST_GET_PROFILES_BY_EMAIL_URL)
        self.assertEqual(kwargs["json"], {"email_address": "user@example.com"})
        self.assertEqual(kwargs["timeout"], HTTP_TIMEOUT_SECONDS)
        self.assertEqual(
            kwargs["headers"]["Authorization"],
            "Bearer test-token",
        )
        self.assertEqual(
            kwargs["headers"]["Origin"],
            "https://lynx-stage.goorange.sixt.com",
        )

    @patch.dict(
        os.environ,
        {"TEST_PARAM_GET_PROFILES_BY_EMAIL_URL": _TEST_GET_PROFILES_BY_EMAIL_URL},
        clear=False,
    )
    @patch("tdm_adapter.requests.post")
    @patch(
        "tdm_adapter.get_client_credentials_access_token",
        return_value="test-token",
    )
    def test_get_profiles_by_email_address_proto_json_camel_case(
        self,
        _mock_token: object,
        mock_post: MagicMock,
    ) -> None:
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.json.return_value = {
            "profiles": [
                {"profileId": "1", "corporateCustomerId": None},
            ],
            "personId": "2",
            "memberId": "M",
        }
        mock_post.return_value = mock_response

        result = get_profiles_by_email_address("a@b.co")

        self.assertEqual(
            result,
            {
                "profiles": [{"profile_id": "1", "corporate_customer_id": ""}],
                "person_id": "2",
                "member_id": "M",
            },
        )

    def test_get_profiles_by_email_address_rejects_blank_email(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            get_profiles_by_email_address("   ")
        self.assertIn("non-empty", str(ctx.exception))

    def test_get_profiles_by_email_address_rejects_non_str_email(self) -> None:
        with self.assertRaises(TypeError) as ctx:
            get_profiles_by_email_address(None)  # type: ignore[arg-type]
        self.assertIn("string", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
