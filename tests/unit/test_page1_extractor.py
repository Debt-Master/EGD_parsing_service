from egd_parser.domain.models.ocr import OCRPageResult
from egd_parser.pipeline.extractors.page1 import extract_page1


SAMPLE_PAGE_1_TEXT = """
Единый жилищный документ (справка о заявителе)
по состоянию на 22.01.2026 г.
Юго-восточный административный округ Район Марьино
ненужное зачеркнуть
ул. Подольская ул. дом № 25 корп. ____ строение ____ кв. 252
Прежнее наименование адреса (в случае замены)
Организация, выполняющая функции управления домом:
ООО "Управление Многоквартирными Домами"
адрес: 109651, страна Россия, г. Москва, ул. Новочеркасский б-р, дом. 20, кор. 3, телефон: +7(495)7294310
Вид заселения:
частная собственность
Ф. И. О. владельца права собственности Доля в праве собственности, %
Гуманцев Андрей Викторович без опред. долей
Гуманцев Виктор Андреевич без опред. долей
на основании:
Выписка из Единого Государственного Реестра прав на недвижимое имущество 99/2020/363749624 от 03.12.2020 выдан ФГИС ЕГРН
(указывается №, дата и кем выдан (оформлен) соответствующий документ)
Характеристика занимаемого жилого помещения:
Площадь жилого помещения (с учетом балконов, лоджий, веранд, террас): 51,60 кв. м.
"""


def test_extract_page1_from_sample_text() -> None:
    result = extract_page1([OCRPageResult(page_number=1, text=SAMPLE_PAGE_1_TEXT)])
    page_1 = result["page_1"]

    assert result["document_type"] == "egd"
    assert page_1["document_date"] == "22.01.2026"
    assert page_1["administrative_okrug"] == "Юго-Восточный административный округ"
    assert page_1["district"] == "Марьино"
    assert page_1["passport"] == {}

    assert page_1["property_address"] == {
        "raw": "ул. Подольская ул. дом № 25 корп. ____ строение ____ кв. 252",
        "full": "ул. Подольская, дом 25, кв. 252",
        "street": "ул. Подольская",
        "house": "25",
        "building": None,
        "structure": None,
        "apartment": "252",
    }

    assert page_1["management_company"] == {
        "name": 'ООО "Управление Многоквартирными Домами"',
        "address": "109651, страна Россия, г. Москва, ул. Новочеркасский б-р, дом 20, корп. 3",
        "phone": "+7(495)729-43-10",
    }

    assert page_1["settlement_type"] == "частная собственность"
    assert page_1["owners"] == [
        {
            "full_name": "Гуманцев Андрей Викторович",
            "ownership_share": "без опред. долей",
        },
        {
            "full_name": "Гуманцев Виктор Андреевич",
            "ownership_share": "без опред. долей",
        },
    ]
    assert page_1["ownership_documents"] == [
        "Выписка из Единого Государственного Реестра прав на недвижимое имущество 99/2020/363749624 от 03.12.2020 выдан ФГИС ЕГРН"
    ]
    assert page_1["total_area_sq_m"] == "51.60"


def test_extract_page1_supports_compound_owner_surname() -> None:
    text = """
    Вид заселения:
    частная собственность
    Ф. И. О. владельца права собственности Доля в праве собственности, %
    Фессенден Людмила Викторовна 50,00
    Де Буард Галина Петровна 50,00
    на основании:
    """

    page_1 = extract_page1([OCRPageResult(page_number=1, text=text)])["page_1"]

    assert page_1["owners"] == [
        {"full_name": "Фессенден Людмила Викторовна", "ownership_share": "50.00"},
        {"full_name": "Де Буард Галина Петровна", "ownership_share": "50.00"},
    ]


def test_extract_page1_supports_patronymic_suffix_and_separate_share_lines() -> None:
    text = """
    Вид заселения:
    частная собственность
    Доля в праве собственности, %
    Ф. И. О. владельца права собственности
    25,00
    Пириев Хайям Идрис оглы
    41,67
    Абдулов Абдулахад Вагабович
    16,67
    Качаева Элина Бургановна
    16,67
    Алиев Сарибек Хамирзаевич
    на основании:
    """

    owners = extract_page1([OCRPageResult(page_number=1, text=text)])["page_1"]["owners"]

    assert owners == [
        {"full_name": "Пириев Хайям Идрис оглы", "ownership_share": "25.00"},
        {"full_name": "Абдулов Абдулахад Вагабович", "ownership_share": "41.67"},
        {"full_name": "Качаева Элина Бургановна", "ownership_share": "16.67"},
        {"full_name": "Алиев Сарибек Хамирзаевич", "ownership_share": "16.67"},
    ]


def test_extract_page1_normalizes_split_street_prefix() -> None:
    text = """
    Заявитель зарегистрирован по месту жительства:
    л. Подольская ул. дом № 33 кв. 30
    Прежнее наименование адреса:
    Вид заселения:
    социальный наем
    """

    address = extract_page1([OCRPageResult(page_number=1, text=text)])["page_1"]["property_address"]

    assert address["street"] == "ул. Подольская"
    assert address["house"] == "33"
    assert address["apartment"] == "30"


def test_extract_passport_data_from_sample_text() -> None:
    text = """
    Паспортные данные:
    паспорт РФ 45 23 998632 выдан ГУ МВД России по г. Москкве 30.01.2024
    Сведения о ранее выданном паспорте:
    """

    result = extract_page1([OCRPageResult(page_number=1, text=text)])

    assert result["page_1"]["passport"] == {
        "raw": "паспорт РФ 45 23 998632 выдан ГУ МВД России по г. Москве 30.01.2024",
        "document_type": "паспорт РФ",
        "series": "45 23",
        "number": "998632",
        "issued_by": "ГУ МВД России по г. Москве",
        "issue_date": "30.01.2024",
    }
