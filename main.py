import argparse
import os
import sys
from typing import Any, Dict, List, Optional

import requests


HERE_URL = "https://revgeocode.search.hereapi.com/v1/revgeocode"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Определение улицы и разрешенной скорости через HERE API"
    )

    parser.add_argument(
        "--latitude",
        required=True,
        type=float,
        help="Широта",
    )

    parser.add_argument(
        "--longitude",
        required=True,
        type=float,
        help="Долгота",
    )

    parser.add_argument(
        "--bearing",
        type=int,
        default=None,
        help="Направление движения в градусах: 0=N, 90=E, 180=S, 270=W",
    )

    return parser.parse_args()


def validate_coordinates(latitude: float, longitude: float):
    if not -90 <= latitude <= 90:
        raise ValueError(
            f"Некорректная широта: {latitude}. "
            "Допустимый диапазон: -90...90."
        )

    if not -180 <= longitude <= 180:
        raise ValueError(
            f"Некорректная долгота: {longitude}. "
            "Допустимый диапазон: -180...180."
        )


def validate_bearing(bearing: Optional[int]):
    if bearing is None:
        return

    if not 0 <= bearing <= 359:
        raise ValueError(
            f"Некорректное направление: {bearing}. "
            "Допустимый диапазон: 0...359."
        )


def get_here_data(
    latitude: float,
    longitude: float,
    bearing: Optional[int] = None,
) -> Dict[str, Any]:

    api_key = os.getenv("HERE_API_KEY")

    if not api_key:
        raise RuntimeError(
            "Не найден секрет HERE_API_KEY. "
            "Добавьте API key в GitHub Secrets."
        )

    params = {
        "at": f"{latitude},{longitude}",
        "showNavAttributes": "speedLimits",
        "showMapReferences": "segments",
        "lang": "ru-RU",
        "limit": 5,
        "apiKey": api_key,
    }

    if bearing is not None:
        params["bearing"] = bearing

    response = requests.get(
        HERE_URL,
        params=params,
        timeout=30,
    )

    if response.status_code != 200:
        try:
            error_data = response.json()
        except ValueError:
            error_data = response.text

        raise RuntimeError(
            f"HERE API вернул HTTP {response.status_code}: "
            f"{error_data}"
        )

    try:
        return response.json()
    except ValueError:
        raise RuntimeError("HERE API вернул некорректный JSON.")


def get_first_item(data: Dict[str, Any]) -> Dict[str, Any]:
    items = data.get("items")

    if not items:
        raise RuntimeError(
            "HERE не вернул ни одной дороги для указанных координат."
        )

    return items[0]


def get_street_name(item: Dict[str, Any]) -> str:
    address = item.get("address", {})

    street = address.get("street")

    if street:
        return street

    title = item.get("title")

    if title:
        return title

    return "Название улицы не определено"


def get_address(item: Dict[str, Any]) -> str:
    address = item.get("address", {})

    label = address.get("label")

    if label:
        return label

    return item.get("title", "Адрес не определен")


def recursive_find_speed_limits(
    value: Any,
    found: Optional[List[Any]] = None,
) -> List[Any]:
    """
    Рекурсивно ищет объекты, связанные с speed limits.

    Это сделано намеренно, поскольку HERE может размещать
    навигационные атрибуты в разных частях ответа.
    """

    if found is None:
        found = []

    if isinstance(value, dict):

        for key, child in value.items():

            key_lower = str(key).lower()

            if "speedlimit" in key_lower:
                found.append(child)

            recursive_find_speed_limits(child, found)

    elif isinstance(value, list):

        for item in value:
            recursive_find_speed_limits(item, found)

    return found


def flatten_speed_values(value: Any) -> List[Any]:
    """
    Преобразует найденные speed limit данные
    в простой список значений.
    """

    result = []

    if isinstance(value, dict):

        for key, child in value.items():

            key_lower = str(key).lower()

            if "speedlimit" in key_lower:
                if child is not None:
                    result.append(
                        {
                            "field": key,
                            "value": child,
                        }
                    )

            else:
                result.extend(flatten_speed_values(child))

    elif isinstance(value, list):

        for item in value:
            result.extend(flatten_speed_values(item))

    return result


def print_speed_information(item: Dict[str, Any]):
    """
    Выводит найденные ограничения скорости.
    """

    speed_data = recursive_find_speed_limits(item)

    if not speed_data:
        print("⚠️ HERE не вернул данные об ограничении скорости.")
        return

    flattened = []

    for entry in speed_data:
        flattened.extend(flatten_speed_values(entry))

    if not flattened:
        print("⚠️ Ограничение скорости не найдено.")
        return

    print()
    print("Ограничения скорости HERE:")

    unique_values = set()

    for entry in flattened:

        field = entry.get("field")
        value = entry.get("value")

        text = f"{field} = {value}"

        if text not in unique_values:
            unique_values.add(text)
            print(f"  • {text}")


def print_result(
    latitude: float,
    longitude: float,
    bearing: Optional[int],
    item: Dict[str, Any],
):

    street = get_street_name(item)
    address = get_address(item)

    print()
    print("=" * 60)
    print("HERE SPEED LIMIT CHECK")
    print("=" * 60)

    print(f"Координаты: {latitude}, {longitude}")

    if bearing is not None:
        print(f"Направление движения: {bearing}°")
    else:
        print("Направление движения: не задано")

    print(f"Улица: {street}")
    print(f"Адрес: {address}")

    print(f"HERE ID: {item.get('id', 'не определен')}")
    print(f"Тип результата: {item.get('resultType', 'не определен')}")

    distance = item.get("distance")

    if distance is not None:
        print(f"Расстояние до найденной дороги: {distance} м")

    print_speed_information(item)

    print("=" * 60)


def main():
    args = parse_args()

    try:
        validate_coordinates(
            args.latitude,
            args.longitude,
        )

        validate_bearing(args.bearing)

        print("Запрашиваем данные HERE...")
        print(
            f"Координаты: "
            f"{args.latitude}, {args.longitude}"
        )

        data = get_here_data(
            args.latitude,
            args.longitude,
            args.bearing,
        )

        item = get_first_item(data)

        print_result(
            args.latitude,
            args.longitude,
            args.bearing,
            item,
        )

    except KeyboardInterrupt:
        print("\nОперация отменена.")
        sys.exit(130)

    except Exception as exc:
        print()
        print(f"❌ ОШИБКА: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()