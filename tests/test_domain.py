from papertrans.domain import BoundingBox


def test_bounding_box_dimensions_and_serialization() -> None:
    bbox = BoundingBox(10.0, 20.0, 42.5, 55.25)

    assert bbox.width == 32.5
    assert bbox.height == 35.25
    assert bbox.to_list() == [10.0, 20.0, 42.5, 55.25]
