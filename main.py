from __future__ import annotations

from tdm_adapter import create_user_and_reservation


def main() -> None:
    _, reservation_number = create_user_and_reservation()
    print(reservation_number)


if __name__ == "__main__":
    main()
