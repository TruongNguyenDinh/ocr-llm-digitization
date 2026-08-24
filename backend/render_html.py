import json
import sys
from pathlib import Path


# ============================================================
# HELPERS
# ============================================================

def bbox_to_rect(bbox):
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]

    return (
        min(xs),
        min(ys),
        max(xs),
        max(ys),
    )


def escape_html(text):
    """
    Basic HTML escaping.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# ============================================================
# FLOW
# ============================================================

def render_flow_element(element):
    """
    Render semantic flow element.

    IMPORTANT:
    Flow elements do NOT use OCR Y coordinates.
    Their position is determined by normal HTML flow.
    """

    element_type = element.get(
        "type",
        "unknown",
    )

    text = escape_html(
        element.get(
            "text",
            "",
        ).strip()
    )

    indent = element.get(
        "indent",
        0,
    )

    # --------------------------------------------------------
    # SALUTATION
    # --------------------------------------------------------

    if element_type == "salutation":

        return f"""
        <div
            class="flow-element salutation"
        >
            {text}
        </div>
        """

    # --------------------------------------------------------
    # PARAGRAPH
    # --------------------------------------------------------

    if element_type == "paragraph":

        indent_style = ""

        if indent and indent > 0:

            indent_style = (
                f"padding-left:{indent}px;"
            )

        return f"""
        <div
            class="flow-element paragraph"
            style="{indent_style}"
        >
            {text}
        </div>
        """

    # --------------------------------------------------------
    # CLOSING
    # --------------------------------------------------------

    if element_type == "closing":

        return f"""
        <div
            class="flow-element closing"
        >
            {text}
        </div>
        """

    # --------------------------------------------------------
    # GENERIC FLOW ELEMENT
    # --------------------------------------------------------

    return f"""
    <div
        class="flow-element {element_type}"
    >
        {text}
    </div>
    """

def render_visual_candidates_flow(
    elements,
    signature,
):
    if not elements:
        return ""

    html = []

    for element in elements:

        bbox = element.get(
            "bbox"
        )

        if not bbox:
            continue

        x1, y1, x2, y2 = bbox_to_rect(
            bbox
        )

        text = escape_html(
            element.get(
                "text",
                "",
            ).strip()
        )

        # ----------------------------------------------------
        # X tương đối với signature
        # ----------------------------------------------------

        signature_x = 0

        if signature:

            signature_bbox = signature.get(
                "bbox"
            )

            if signature_bbox:

                sx1, _, _, _ = bbox_to_rect(
                    signature_bbox
                )

                signature_x = (
                    x1 - sx1
                )

        html.append(
            f"""
            <div
                class="visual-flow"
                style="
                    left:{signature_x}px;
                "
            >
                {text}
            </div>
            """
        )

    return "".join(html)
def render_flow(
    layout,
    signature=None,
    visual_candidates=None,
    content_x=0,
):
    flow = layout.get(
        "flow",
        []
    )

    visual_candidates = (
        visual_candidates or []
    )

    elements_html = []

    # --------------------------------------------------------
    # SIGNATURE X
    # --------------------------------------------------------

    signature_x = 0

    if signature:

        bbox = signature.get(
            "bbox"
        )

        if bbox:

            x1, _, _, _ = bbox_to_rect(
                bbox
            )

            signature_x = max(
                0,
                x1 - content_x,
            )

    # --------------------------------------------------------
    # FLOW ELEMENTS
    # --------------------------------------------------------

    for element in flow:

        element_type = element.get(
            "type",
            "unknown",
        )

        text = escape_html(
            element.get(
                "text",
                "",
            ).strip()
        )

        indent = element.get(
            "indent",
            0,
        )

        # ----------------------------------------------------
        # CLOSING
        # ----------------------------------------------------

        if element_type == "closing":

            elements_html.append(
                f"""
                <div
                    class="closing-group"
                    style="
                        margin-left:{signature_x}px;
                    "
                >

                    <div
                        class="flow-element closing"
                    >
                        {text}
                    </div>

                    <div
                        class="signature-flow"
                    >
                        {
                            escape_html(
                                signature.get(
                                    "text",
                                    "",
                                ).strip()
                            )
                            if signature
                            else ""
                        }
                    </div>

                    {
                        render_visual_candidates_flow(
                            visual_candidates,
                            signature,
                        )
                    }

                </div>
                """
            )

            continue

        # ----------------------------------------------------
        # NORMAL FLOW
        # ----------------------------------------------------

        style = ""

        if (
            element_type == "paragraph"
            and indent
        ):

            style = (
                f' style="'
                f'margin-left:{indent}px;"'
            )

        elements_html.append(
            f"""
            <div
                class="flow-element {element_type}"
                {style}
            >
                {text}
            </div>
            """
        )

    # --------------------------------------------------------
    # SIGNATURE FALLBACK
    # --------------------------------------------------------

    if (
        signature
        and not any(
            e.get("type") == "closing"
            for e in flow
        )
    ):

        elements_html.append(
            f"""
            <div
                class="signature-flow"
                style="
                    margin-left:{signature_x}px;
                "
            >
                {
                    escape_html(
                        signature.get(
                            "text",
                            "",
                        ).strip()
                    )
                }
            </div>
            """
        )

    if not elements_html:

        return ""

    return f"""
    <div class="document-flow">
        {''.join(elements_html)}
    </div>
    """

# ============================================================
# FLOATING
# ============================================================

def render_floating_element(
    element,
):
    """
    Render floating element using its original
    OCR bbox.

    Floating elements:
        signature
        visual_candidate
        image
        logo
        stamp
        table
        figure
    """

    bbox = element.get(
        "bbox"
    )

    if not bbox:
        return ""

    x1, y1, x2, y2 = bbox_to_rect(
        bbox
    )

    width = x2 - x1
    height = y2 - y1

    element_type = element.get(
        "type",
        "unknown",
    )

    text = escape_html(
        element.get(
            "text",
            "",
        ).strip()
    )

    # --------------------------------------------------------
    # VISUAL
    # --------------------------------------------------------

    if element_type == "visual_candidate":

        return f"""
        <div
            class="floating visual"
            style="
                left:{x1}px;
                top:{y1}px;
                width:{width}px;
                height:{height}px;
            "
        >
            {text}
        </div>
        """

    # --------------------------------------------------------
    # SIGNATURE
    # --------------------------------------------------------

    if element_type == "signature":

        # Use the center of the OCR bbox as the anchor.
        # This compensates for the different font metrics
        # between the original handwriting and HTML text.

        center_x = (x1 + x2) / 2
        center_y = (y1 + y2) / 2

        return f"""
        <div
            class="floating signature"
            style="
                left:{center_x}px;
                top:{center_y}px;
                width:{width}px;
                height:{height}px;
                transform:translate(-50%, -50%);
            "
        >
            {text}
        </div>
        """

    # --------------------------------------------------------
    # GENERIC FLOATING ELEMENT
    # --------------------------------------------------------

    return f"""
    <div
        class="floating {element_type}"
        style="
            left:{x1}px;
            top:{y1}px;
            width:{width}px;
            height:{height}px;
        "
    >
        {text}
    </div>
    """


def render_floating(
    layout,
):
    """
    Render floating elements independently
    from document flow.
    """

    floating = layout.get(
        "floating",
        [],
    )

    elements = []

    for element in floating:

        html = render_floating_element(
            element
        )

        if html:
            elements.append(
                html
            )

    return "".join(
        elements
    )

def render_signature_flow(
    signature,
    content_x,
):
    if not signature:
        return ""

    text = escape_html(
        signature.get(
            "text",
            "",
        ).strip()
    )

    bbox = signature.get(
        "bbox"
    )

    if bbox:
        x1, _, _, _ = bbox_to_rect(
            bbox
        )

        offset_x = max(
            0,
            x1 - content_x
        )
    else:
        offset_x = 0

    return f"""
    <div
        class="signature-flow"
        style="
            margin-left:{offset_x}px;
        "
    >
        {text}
    </div>
    """

# ============================================================
# PAGE
# ============================================================

def render_page(
    page,
    output_dir,
):
    """
    Render one page from Layout IR.

    Flow elements are rendered using normal HTML flow.
    Signature is treated as the final flow element.
    Other floating elements keep their spatial position.
    """

    width = (
        page.get("width")
        or 2000
    )

    height = (
        page.get("height")
        or 2000
    )

    source_image = page.get(
        "source_image"
    )

    layout = page.get(
        "layout",
        {},
    )

    content = layout.get(
        "content",
        {},
    )

    # --------------------------------------------------------
    # CONTENT CONTAINER
    # --------------------------------------------------------

    content_x = content.get(
        "x",
        0,
    )

    content_y = content.get(
        "y",
        0,
    )

    content_width = content.get(
        "width",
        width,
    )

    # --------------------------------------------------------
    # BACKGROUND
    # --------------------------------------------------------

    image_html = ""

    if source_image:

        image_html = f"""
        <img
            src="{source_image}"
            class="background"
        />
        """

    # --------------------------------------------------------
    # FLOATING ELEMENTS
    # --------------------------------------------------------

    floating = layout.get(
        "floating",
        []
    )

    signature = None
    visual_candidates = []
    other_floating = []

    for element in floating:

        element_type = element.get(
            "type",
            "unknown",
        )

        if element_type == "signature":

            signature = element

        elif element_type == "visual_candidate":

            visual_candidates.append(
                element
            )

        else:

            other_floating.append(
                element
            )

    # --------------------------------------------------------
    # FLOW
    # --------------------------------------------------------

    flow_html = render_flow(
        layout,
        signature=signature,
        visual_candidates=visual_candidates,
        content_x=content_x,
    )
    # --------------------------------------------------------
    # OTHER FLOATING ELEMENTS
    # --------------------------------------------------------

    floating_html = ""

    if other_floating:
        floating_html = render_floating(
            {
                "floating": other_floating
            }
        )

    # --------------------------------------------------------
    # DOCUMENT TYPE
    # --------------------------------------------------------

    document_type = page.get(
        "document_type",
        "",
    )

    if not document_type:

        document_type = layout.get(
            "document_type",
            "unknown",
        )

    # --------------------------------------------------------
    # HTML
    # --------------------------------------------------------

    html = f"""<!DOCTYPE html>
<html>

<head>

<meta charset="UTF-8">

<title>
OCR Document
</title>

<style>

/* ==========================================================
   PAGE
   ========================================================== */

html,
body {{
    margin: 0;
    padding: 0;
}}

body {{
    background: #eeeeee;
}}

.page {{
    position: relative;

    width: {width}px;
    height: {height}px;

    margin: 0 auto;

    overflow: hidden;

    background: white;
}}


/* ==========================================================
   ORIGINAL IMAGE
   ========================================================== */

.background {{
    position: absolute;

    left: 0;
    top: 0;

    width: {width}px;
    height: {height}px;

    object-fit: fill;

    z-index: 0;
}}


/* ==========================================================
   DOCUMENT FLOW
   ========================================================== */

.document-flow {{

    position: absolute;

    left: {content_x}px;
    top: {content_y}px;

    width: {content_width}px;

    z-index: 10;

    box-sizing: border-box;

    font-family:
        Arial,
        sans-serif;

    color: #111;

}}


/* ==========================================================
   COMMON FLOW ELEMENT
   ========================================================== */

.flow-element {{

    box-sizing: border-box;

    margin: 0;
    padding: 0;

    white-space: normal;

    overflow-wrap: normal;

    word-break: normal;

}}


/* ==========================================================
   SALUTATION
   ========================================================== */

.salutation {{

    font-size: 32px;

    line-height: 1.2;

    margin: 0 0 28px 0;

}}


/* ==========================================================
   PARAGRAPH
   ========================================================== */

.paragraph {{

    font-size: 27px;

    line-height: 1.45;

    margin: 0 0 24px 0;

}}


/* ==========================================================
   CLOSING
   ========================================================== */

.closing {{

    font-size: 30px;

    line-height: 1.2;

    margin: 0 0 18px 0;

}}
.closing-group {{
    position: relative;
    box-sizing: border-box;
    margin: 0 0 0 0;
}}

.signature-flow {{
    box-sizing: border-box;

    font-family:
        Arial,
        sans-serif;

    font-size: 32px;

    line-height: 1.2;

    font-style: italic;

    white-space: nowrap;

    margin: 0;
    padding: 0;
}}

.visual-flow {{
    position: absolute;

    left: 0;

    top: 50%;

    transform:
        translateY(-50%);

    box-sizing: border-box;

    font-family:
        Arial,
        sans-serif;

    font-size: 28px;

    line-height: 1.2;

    white-space: nowrap;

    color: red;
}}

/* ==========================================================
   SIGNATURE IN FLOW
   ========================================================== */

.signature-flow {{

    box-sizing: border-box;

    font-family:
        Arial,
        sans-serif;

    font-size: 32px;

    line-height: 1.2;

    font-style: italic;

    white-space: nowrap;

    margin: 0;

    padding: 0;

}}


/* ==========================================================
   FLOATING
   ========================================================== */

.floating {{

    position: absolute;

    box-sizing: border-box;

    z-index: 20;

    font-family:
        Arial,
        sans-serif;

}}


/* ==========================================================
   VISUAL CANDIDATE
   ========================================================== */

.visual {{

    border: 2px dashed red;

    color: red;

    font-size: 28px;

    line-height: 1.2;

}}


/* ==========================================================
   DEBUG
   ========================================================== */

.page.debug .document-flow {{

    outline: 2px solid blue;

}}

</style>

</head>


<body>

<div
    class="page"
    data-document-type="{escape_html(document_type)}"
>

    {image_html}

    {flow_html}

    {floating_html}

</div>

</body>

</html>
"""

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = (
        output_dir
        / f"page_{page['page']:03d}.html"
    )

    output.write_text(
        html,
        encoding="utf-8",
    )

    return output


# ============================================================
# MAIN
# ============================================================

def main():

    if len(sys.argv) != 3:

        print(
            "Usage: "
            "python -m backend.render_html "
            "<input_layout.json> "
            "<output_dir>"
        )

        sys.exit(1)

    input_path = Path(
        sys.argv[1]
    )

    output_dir = Path(
        sys.argv[2]
    )

    with open(
        input_path,
        encoding="utf-8",
    ) as f:

        data = json.load(f)

    document_type = data.get(
        "document_type",
        "unknown",
    )

    print(
        f"Document type: "
        f"{document_type}"
    )

    for page in data.get(
        "pages",
        [],
    ):

        # ----------------------------------------------------
        # Layout IR
        # ----------------------------------------------------

        layout = page.get(
            "layout",
            {},
        )

        # Pass document type down
        # for renderer/debugging.
        page["document_type"] = (
            document_type
        )

        output = render_page(
            page,
            output_dir,
        )

        print(
            f"Rendered: {output}"
        )

        print(
            f"  Flow: "
            f"{len(layout.get('flow', []))}"
        )

        print(
            f"  Floating: "
            f"{len(layout.get('floating', []))}"
        )


if __name__ == "__main__":
    main()