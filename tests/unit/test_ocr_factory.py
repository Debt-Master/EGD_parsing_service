from pathlib import Path

from egd_parser.infrastructure.ocr.factory import common_model_base_dir, resolve_model_dir


def test_resolve_model_dir_falls_back_to_packaged_models() -> None:
    model_dir = resolve_model_dir(Path("/missing/PP-OCRv5_mobile_det_infer"))

    assert model_dir.name == "PP-OCRv5_mobile_det_infer"
    assert (model_dir / "inference.json").is_file()


def test_common_model_base_dir_returns_shared_parent() -> None:
    det_dir = resolve_model_dir(Path("/missing/PP-OCRv5_mobile_det_infer"))
    rec_dir = resolve_model_dir(Path("/missing/cyrillic_PP-OCRv5_mobile_rec_infer"))

    assert common_model_base_dir(det_dir, rec_dir) == det_dir.parent
