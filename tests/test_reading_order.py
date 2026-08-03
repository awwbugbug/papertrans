from papertrans.domain import BoundingBox, Document, Page, Region, RegionType, TextStyle
from papertrans.structure.reading_order import recover_document_structure, recover_page_structure


def _region(
    region_id: str,
    text: str,
    bbox: tuple[float, float, float, float],
    region_type: RegionType = RegionType.PARAGRAPH,
    font_size: float = 10,
) -> Region:
    return Region(
        id=region_id,
        type=region_type,
        bbox=BoundingBox(*bbox),
        source_text=text,
        style=TextStyle(font_name="Test", font_size=font_size),
    )


def test_two_column_order_and_special_region_classification() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("title", "A Paper", (250, 50, 350, 75), RegionType.TITLE, 18),
            _region("author", "Ada Author", (260, 90, 340, 108), RegionType.HEADING, 12),
            _region("abstract-heading", "Abstract", (60, 140, 130, 158), RegionType.HEADING, 12),
            _region("figure-label", "accuracy (%)", (420, 145, 480, 160), font_size=7),
            _region(
                "figure-caption",
                "Figure 1. Accuracy over time.",
                (320, 180, 550, 205),
            ),
            _region("abstract", "The abstract is in the left column.", (50, 170, 280, 260)),
            _region("right-body", "Right column continuation.", (320, 280, 550, 390)),
            _region("intro", "1. Introduction", (50, 300, 180, 320), RegionType.HEADING, 12),
            _region("left-body", "Left column comes first.", (50, 340, 280, 500)),
            _region("stamp", "arXiv:1234.5678", (10, 180, 30, 520), RegionType.TITLE, 11),
        ],
    )

    recover_page_structure(page)

    assert page.metadata["layout"] == "two_column"
    by_id = {region.id: region for region in page.regions}
    assert by_id["author"].type == RegionType.AUTHOR
    assert by_id["abstract"].type == RegionType.ABSTRACT
    assert by_id["figure-caption"].type == RegionType.FIGURE_CAPTION
    assert by_id["figure-label"].type == RegionType.FIGURE_TEXT
    assert by_id["figure-label"].reading_order is None
    assert by_id["stamp"].type == RegionType.HEADER
    assert by_id["stamp"].reading_order is None
    assert by_id["left-body"].reading_order < by_id["right-body"].reading_order


def test_asymmetric_figure_and_text_page_is_two_column() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("caption", "Figure 3. Network architecture.", (50, 650, 280, 700)),
            _region("right-1", "Right column paragraph one.", (320, 80, 550, 260)),
            _region("right-2", "Right column paragraph two.", (320, 300, 550, 480)),
        ],
    )

    recover_page_structure(page)

    assert page.metadata["layout"] == "two_column"


def test_short_ocr_lines_still_provide_two_column_evidence() -> None:
    regions = [
        _region("left-1", "Left academic line one", (50, 100, 280, 110)),
        _region("left-2", "Left academic line two", (50, 114, 280, 124)),
        _region("right-1", "Right academic line one", (320, 100, 550, 110)),
        _region("right-2", "Right academic line two", (320, 114, 550, 124)),
    ]
    for region in regions:
        region.metadata["content_source"] = "paddleocr"
    page = Page(number=1, width=600, height=800, regions=regions)

    recover_page_structure(page)

    assert page.metadata["layout"] == "two_column"
    by_id = {region.id: region for region in page.regions}
    assert by_id["left-1"].metadata["column_index"] == 1
    assert by_id["right-1"].metadata["column_index"] == 2
    assert by_id["left-2"].reading_order < by_id["right-1"].reading_order


def test_reference_section_continues_across_pages_and_is_protected() -> None:
    first_page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("references", "References", (50, 100, 180, 125), RegionType.HEADING, 12),
            _region("ref-1", "[1] First reference.", (50, 150, 280, 220)),
        ],
    )
    second_page = Page(
        number=2,
        width=600,
        height=800,
        regions=[_region("ref-2", "[2] Second reference.", (50, 80, 280, 160))],
    )
    document = Document(source_path="fixture.pdf", pages=[first_page, second_page])

    recover_document_structure(document)

    by_id = {region.id: region for page in document.pages for region in page.regions}
    assert by_id["ref-1"].type == RegionType.REFERENCE
    assert by_id["ref-2"].type == RegionType.REFERENCE
    assert by_id["ref-1"].translatable is False
    assert by_id["ref-2"].translatable is False


def test_table_rows_below_caption_are_protected() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("caption", "Table 1. Accuracy results.", (50, 100, 280, 125)),
            _region("row", "method score accuracy", (70, 140, 260, 170), font_size=7),
            _region("body", "Normal paragraph text.", (50, 400, 280, 520)),
        ],
    )

    recover_page_structure(page)

    by_id = {region.id: region for region in page.regions}
    assert by_id["caption"].type == RegionType.TABLE_CAPTION
    assert by_id["row"].type == RegionType.TABLE_TEXT
    assert by_id["row"].translatable is False
    assert by_id["row"].reading_order is None


def test_table_rows_above_caption_are_protected_without_hiding_body_below() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region(
                "table-header",
                "method train set aero bike bird boat mAP",
                (50, 100, 550, 110),
                font_size=7,
            ),
            _region(
                "table-row",
                "FRCN 07+12 77.0 78.1 69.3 70.0",
                (50, 114, 550, 124),
                font_size=7,
            ),
            _region(
                "caption",
                "Table 1. Detection average precision results.",
                (50, 132, 550, 154),
                font_size=9,
            ),
            _region(
                "left-body",
                "This normal body paragraph begins below the table caption and must translate.",
                (50, 176, 280, 276),
                font_size=10,
            ),
            _region(
                "right-body",
                "The second column is also prose rather than table content.",
                (320, 176, 550, 276),
                font_size=10,
            ),
        ],
    )
    for region in page.regions[:2]:
        region.metadata["native_lines"] = [
            {"bbox": [50 + index * 28, region.bbox.y0, 70 + index * 28, region.bbox.y1]}
            for index in range(17)
        ]

    recover_page_structure(page)

    by_id = {region.id: region for region in page.regions}
    for region_id in ("table-header", "table-row"):
        assert by_id[region_id].type == RegionType.TABLE_TEXT
        assert by_id[region_id].translatable is False
    for region_id in ("left-body", "right-body"):
        assert by_id[region_id].type == RegionType.PARAGRAPH
        assert by_id[region_id].translatable is True


def test_body_sized_numeric_table_block_remains_protected() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("caption", "Table 2. Segmentation results.", (50, 100, 300, 125)),
            _region(
                "table-values",
                "FCN-32s 63.8 42.7 31.8 48.3 FCN-16s 65.7 46.2 34.8 50.7",
                (70, 140, 290, 210),
                font_size=10,
            ),
            _region(
                "body",
                "This ordinary body paragraph contains model 3 and Section 5.2 references.",
                (50, 400, 280, 520),
                font_size=10,
            ),
        ],
    )

    recover_page_structure(page)

    by_id = {region.id: region for region in page.regions}
    assert by_id["table-values"].type == RegionType.TABLE_TEXT
    assert by_id["table-values"].translatable is False
    assert by_id["body"].type == RegionType.PARAGRAPH
    assert by_id["body"].translatable is True


def test_math_heavy_block_is_protected_as_formula() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("formula", "L(p, u) = -log p_u + λ ||t-v||^2", (50, 200, 280, 240)),
            _region(
                "body", "This is normal paragraph text with enough words.", (50, 300, 280, 400)
            ),
        ],
    )

    recover_page_structure(page)

    by_id = {region.id: region for region in page.regions}
    assert by_id["formula"].type == RegionType.FORMULA
    assert by_id["formula"].translatable is False
    assert by_id["formula"].reading_order is None


def test_short_accented_variable_is_protected_as_formula() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("formula", "ˆhi", (245, 131, 253, 141), font_size=7),
            _region(
                "body", "This is normal paragraph text with enough words.", (50, 300, 280, 400)
            ),
        ],
    )

    recover_page_structure(page)

    by_id = {region.id: region for region in page.regions}
    assert by_id["formula"].type == RegionType.FORMULA
    assert by_id["formula"].translatable is False
    assert by_id["formula"].reading_order is None


def test_split_equation_fragments_and_label_are_protected_as_one_cluster() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("label", "loss function:", (50, 74, 104, 84)),
            _region("sum", "S2\nX", (79, 95, 90, 109), font_size=7),
            _region("index", "i=0", (79, 114, 90, 119), font_size=5),
            _region("variable", "p", (105, 102, 110, 109), font_size=7),
            _region("explanation", "where the object appears in a cell", (50, 245, 270, 270)),
        ],
    )

    recover_page_structure(page)

    by_id = {region.id: region for region in page.regions}
    for region_id in ("label", "sum", "index", "variable"):
        assert by_id[region_id].type == RegionType.FORMULA
        assert by_id[region_id].translatable is False
        assert by_id[region_id].reading_order is None
    assert by_id["explanation"].type == RegionType.PARAGRAPH
    assert by_id["explanation"].translatable is True


def test_symbol_heavy_heading_fragment_is_protected_as_formula() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("figure-fragment", "} ×4\n} ×2", (308, 190, 369, 206), RegionType.HEADING),
        ],
    )

    recover_page_structure(page)

    region = page.regions[0]
    assert region.type == RegionType.FORMULA
    assert region.translatable is False
    assert region.reading_order is None


def test_piecewise_formula_branch_is_protected_with_adjacent_formula() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region("formula", "φ(x) =", (112, 677, 142, 687)),
            _region(
                "branch",
                "x,\nif x > 0\n0.1x,\notherwise\n(2)",
                (153, 671, 286, 696),
            ),
        ],
    )

    recover_page_structure(page)

    by_id = {region.id: region for region in page.regions}
    assert by_id["formula"].type == RegionType.FORMULA
    assert by_id["branch"].type == RegionType.FORMULA
    assert by_id["branch"].translatable is False


def test_bulleted_metric_formula_is_protected() -> None:
    page = Page(
        number=1,
        width=600,
        height=800,
        regions=[
            _region(
                "metric",
                "i ti\n• mean accuracy: (1/ncl) ∑ i nii/ti",
                (319, 372, 455, 414),
            ),
        ],
    )

    recover_page_structure(page)

    region = page.regions[0]
    assert region.type == RegionType.FORMULA
    assert region.translatable is False
