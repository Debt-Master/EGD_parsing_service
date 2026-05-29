from egd_parser.pipeline.runner import find_best_candidate_name, normalize_registered_full_name


def test_normalize_registered_full_name_fixes_joined_name_and_patronymic() -> None:
    assert normalize_registered_full_name("Наумова Вален тинаФоминична") == "Наумова Валентина Фоминична"


def test_normalize_registered_full_name_fixes_broken_patronymic_suffixes() -> None:
    assert normalize_registered_full_name("Пучков Константин Валентиноб") == "Пучков Константин Валентинович"
    assert normalize_registered_full_name("Иванов Александр Михайлоб") == "Иванов Александр Михайлович"
    assert normalize_registered_full_name("Данильченко Дмитрий Юрьеб") == "Данильченко Дмитрий Юрьевич"


def test_normalize_registered_full_name_applies_confirmed_overrides() -> None:
    assert normalize_registered_full_name("Мосын у гин") == "Сутугин Павел Михайлович"
    assert normalize_registered_full_name("Амбарцумян Роберт Арменакоб") == "Амбарцумян Арианна Арменаковна"
    assert normalize_registered_full_name("Григорян Айрин") == "Григорян Айрин Романовна"
    assert normalize_registered_full_name("Ахмади Фришта Афгани-") == "Ахмади Фришта"


def test_find_best_candidate_name_repairs_single_ocr_substitution_in_surname() -> None:
    assert (
        find_best_candidate_name("Фончаров Игорь Борисович", ["Гончаров Игорь Борисович"])
        == "Гончаров Игорь Борисович"
    )
