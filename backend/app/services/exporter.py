"""Export service for articles and daily briefings - Markdown and PDF."""

import logging
from datetime import datetime
from pathlib import Path

from app.config import BASE_DIR

logger = logging.getLogger(__name__)


def export_articles_markdown(articles) -> str:
    """Convert a list of articles to Markdown format."""
    lines = []
    lines.append("# RSS Reader - Exported Articles\n")
    lines.append(f"*Exported on: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    lines.append("---\n")

    for article in articles:
        lines.append(f"## [{article.title}]({article.url})\n")
        if article.author:
            lines.append(f"**Author**: {article.author}  \n")
        if article.feed:
            lines.append(f"**Source**: {article.feed.title}  \n")
        if article.published_at:
            lines.append(f"**Published**: {article.published_at.strftime('%Y-%m-%d %H:%M')}  \n")
        lines.append("")
        if article.summary:
            lines.append(f"**Summary**: {article.summary}\n")
        lines.append("---\n")
        lines.append("")

    return "\n".join(lines)


def markdown_to_pdf(markdown_content: str, output_path: str | Path) -> bool:
    """Convert Markdown content to PDF using weasyprint."""
    try:
        # Convert Markdown to HTML first
        html_content = _markdown_to_html(markdown_content)

        # Use weasyprint to convert HTML to PDF
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
        return True
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        return False


def _markdown_to_html(md: str) -> str:
    """Simple Markdown to HTML conversion for basic formatting."""
    import html as html_mod

    lines = md.split("\n")
    html_lines = []
    in_list = False

    for line in lines:
        line = line.rstrip()

        # Headers
        if line.startswith("## "):
            html_lines.append(f"<h2>{html_mod.escape(line[3:])}</h2>")
        elif line.startswith("# "):
            html_lines.append(f"<h1>{html_mod.escape(line[2:])}</h1>")

        # Horizontal rule
        elif line == "---":
            html_lines.append("<hr>")

        # Bold and italic
        elif line.startswith("**") and line.endswith("**"):
            html_lines.append(f"<p><strong>{html_mod.escape(line.strip('*'))}</strong></p>")

        # Links
        elif "](http" in line:
            import re
            def replace_link(m):
                text = m.group(1)
                url = m.group(2)
                return f'<a href="{url}">{html_mod.escape(text)}</a>'
            line = re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)', replace_link, line)
            html_lines.append(f"<p>{line}</p>")

        # Empty line
        elif line == "":
            html_lines.append("<br>")

        # Regular paragraph
        else:
            html_lines.append(f"<p>{html_mod.escape(line)}</p>")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', sans-serif; max-width: 800px; margin: 0 auto; padding: 2em; line-height: 1.8; color: #333; }}
h1 {{ color: #0ea5e9; border-bottom: 2px solid #e2e8f0; padding-bottom: 0.5em; }}
h2 {{ color: #0f172a; margin-top: 1.5em; }}
a {{ color: #0ea5e9; }}
hr {{ border: none; border-top: 1px solid #e2e8f0; margin: 2em 0; }}
p {{ margin: 0.5em 0; }}
strong {{ color: #0f172a; }}
img {{ max-width: 100%; }}
</style>
</head>
<body>
{"".join(html_lines)}
</body>
</html>"""
    return html
