"""Editable, programmatically generated HackPack visual theme."""
from pptx import Presentation
from pptx.util import Inches
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

NAVY = RGBColor(15, 12, 41)  # #0F0C29 solid dark background
PANEL = RGBColor(27, 32, 58)
PURPLE = RGBColor(108, 99, 255)  # electric violet accent
CYAN = RGBColor(0, 217, 255)  # cyan accent
WHITE = RGBColor(248, 249, 255)
MUTED = RGBColor(184, 191, 215)


def create_hackpack_template() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    prs.core_properties.title = "HackPack Pitch Deck"
    prs.core_properties.subject = "Generated hackathon pitch deck"
    prs.core_properties.author = "HackPack"
    return prs


def add_base_slide(prs: Presentation, slide_number: int, project_name: str, section: str):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = NAVY

    # Editable background accents rather than raster images.
    stripe = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(0.12), Inches(7.5))
    stripe.fill.solid()
    stripe.fill.fore_color.rgb = PURPLE
    stripe.line.fill.background()

    top_label = slide.shapes.add_textbox(Inches(0.68), Inches(0.32), Inches(8.5), Inches(0.32))
    tf = top_label.text_frame
    tf.clear()
    tf.margin_left = Inches(0)
    tf.margin_right = Inches(0)
    p = tf.paragraphs[0]
    p.text = f"HACKPACK   /   {project_name[:48]}"
    p.font.name = "Aptos"
    p.font.size = __import__("pptx").util.Pt(10)
    p.font.bold = True
    p.font.color.rgb = CYAN

    badge = slide.shapes.add_textbox(Inches(10.3), Inches(0.32), Inches(2.35), Inches(0.3))
    btf = badge.text_frame
    btf.clear()
    btf.margin_left = Inches(0)
    btf.margin_right = Inches(0)
    bp = btf.paragraphs[0]
    bp.text = section.upper()[:30]
    bp.alignment = 2  # right
    bp.font.name = "Aptos"
    bp.font.size = __import__("pptx").util.Pt(9)
    bp.font.bold = True
    bp.font.color.rgb = MUTED

    footer = slide.shapes.add_textbox(Inches(0.68), Inches(7.12), Inches(12.0), Inches(0.2))
    ftf = footer.text_frame
    ftf.clear()
    ftf.margin_left = Inches(0)
    ftf.margin_right = Inches(0)
    fp = ftf.paragraphs[0]
    fp.text = f"{section.upper()}                                      {slide_number:02d}  /  HACKPACK"
    fp.font.name = "Aptos"
    fp.font.size = __import__("pptx").util.Pt(8)
    fp.font.color.rgb = MUTED
    return slide


def add_accent_panel(slide):
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.68), Inches(5.97), Inches(11.95), Inches(0.62))
    panel.fill.solid()
    panel.fill.fore_color.rgb = PANEL
    panel.line.color.rgb = PANEL
    dot = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.68), Inches(5.97), Inches(0.07), Inches(0.62))
    dot.fill.solid()
    dot.fill.fore_color.rgb = CYAN
    dot.line.fill.background()


def add_title(slide, title: str, subtitle: str | None = None):
    from pptx.util import Pt
    shape = slide.shapes.add_textbox(Inches(0.68), Inches(0.9), Inches(11.9), Inches(0.85))
    tf = shape.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(0)
    tf.margin_right = Inches(0)
    tf.margin_top = Inches(0)
    tf.margin_bottom = Inches(0)
    p = tf.paragraphs[0]
    p.text = title[:100]
    p.font.name = "Aptos Display"
    p.font.size = Pt(30 if len(title) < 54 else 26)
    p.font.bold = True
    p.font.color.rgb = WHITE
    if subtitle:
        box = slide.shapes.add_textbox(Inches(0.72), Inches(1.72), Inches(11.5), Inches(0.48))
        stf = box.text_frame
        stf.clear()
        stf.word_wrap = True
        stf.margin_left = Inches(0)
        stf.margin_right = Inches(0)
        p2 = stf.paragraphs[0]
        p2.text = subtitle[:180]
        p2.font.name = "Aptos"
        p2.font.size = Pt(13)
        p2.font.color.rgb = MUTED


def add_bullets(slide, bullets: list[str]):
    from pptx.util import Pt
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.68), Inches(2.3), Inches(11.95), Inches(3.42))
    box.fill.solid()
    box.fill.fore_color.rgb = PANEL
    box.line.color.rgb = PANEL
    textbox = slide.shapes.add_textbox(Inches(1.0), Inches(2.52), Inches(11.25), Inches(3.0))
    tf = textbox.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(0.04)
    tf.margin_right = Inches(0.04)
    tf.margin_top = Inches(0.03)
    tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    values = bullets[:4] if bullets else ["Add project-specific details before presenting."]
    for index, bullet in enumerate(values):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        text = str(bullet).strip()
        if len(text) > 150:
            text = text[:147].rstrip() + "..."
        p.text = f"•  {text}"
        p.font.name = "Aptos"
        p.font.size = Pt(16)
        p.font.color.rgb = WHITE
        p.space_after = Pt(11)
        p.level = 0


def add_evidence_footer(slide, sources: list[str]):
    from pptx.util import Pt
    if not sources:
        return
    box = slide.shapes.add_textbox(Inches(0.75), Inches(6.04), Inches(11.65), Inches(0.43))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = Inches(0.12)
    tf.margin_right = Inches(0.04)
    p = tf.paragraphs[0]
    p.text = "Evidence: " + " · ".join(dict.fromkeys(sources))[:175]
    p.font.name = "Aptos"
    p.font.size = Pt(9)
    p.font.color.rgb = MUTED
