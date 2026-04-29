from __future__ import annotations

from tdm_adapter import get_otp_code


def main() -> None:
    otp = get_otp_code("selvin.dhavidhu+zenqa@sixt.com")
    print(otp)


if __name__ == "__main__":
    main()
