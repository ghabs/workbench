#!/usr/bin/env python3
"""
Regenerate README.md from the Workbench folder structure.
Run this after adding new entries to update the index.
"""

import os
from pathlib import Path
from datetime import datetime
import re

WORKBENCH_DIR = Path(__file__).parent.parent
EXCLUDED_DIRS = {'.git', '.github', '_site', 'scripts', '__pycache__'}

def get_title_from_file(filepath):
    """Extract title from frontmatter or first H1 in markdown file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            # Check for frontmatter title
            if content.startswith('---'):
                end = content.find('---', 3)
                if end != -1:
                    frontmatter = content[3:end]
                    for line in frontmatter.split('\n'):
                        if line.startswith('title:'):
                            return line[6:].strip().strip('"\'')
            # Fallback to first H1
            for line in content.split('\n'):
                if line.startswith('# '):
                    return line[2:].strip()
    except:
        pass
    # Fallback to filename
    return filepath.stem.replace('-', ' ').title()

def get_date_from_file(filepath):
    """Try to extract date from file, fallback to mtime."""
    try:
        with open(filepath, 'r') as f:
            content = f.read(500)
            # Look for date patterns like 2026-01-31
            match = re.search(r'(\d{4}-\d{2}-\d{2})', content)
            if match:
                return match.group(1)
    except:
        pass
    # Fallback to file modification time
    mtime = os.path.getmtime(filepath)
    return datetime.fromtimestamp(mtime).strftime('%Y-%m-%d')

def build_index():
    """Build the Workbench index."""
    categories = {}

    for item in sorted(WORKBENCH_DIR.iterdir()):
        if item.is_dir() and item.name not in EXCLUDED_DIRS and not item.name.startswith('_'):
            entries = []
            for md_file in sorted(item.glob('*.md')):
                title = get_title_from_file(md_file)
                date = get_date_from_file(md_file)
                rel_path = md_file.relative_to(WORKBENCH_DIR)
                entries.append((title, str(rel_path), date))

            if entries:
                categories[item.name] = entries

    return categories

def generate_index(categories):
    """Generate index.md content with Jekyll frontmatter."""
    lines = [
        "---",
        "layout: home",
        "title: Workbench",
        "---",
        "",
        "Tools, scripts, and workflow improvements I'm building - published as I go.",
        "",
        "---",
        ""
    ]

    # Count total
    total = sum(len(entries) for entries in categories.values())
    lines.append(f"_{total} project{'s' if total != 1 else ''} so far._")
    lines.append("")

    # Categories
    for category in sorted(categories.keys()):
        entries = categories[category]
        # Format category name
        display_name = category.replace('-', ' ').title()
        lines.append(f"## {display_name}")
        lines.append("")
        for title, path, date in sorted(entries, key=lambda x: x[2], reverse=True):
            lines.append(f"- [{title}]({path}) - {date}")
        lines.append("")

    # Footer
    lines.extend([
        "---",
        "",
        "## About",
        "",
        "This is where I document the tools and systems I build to improve how I work. Not polished blog posts—practical write-ups on things I've actually built and use.",
        "",
        "Inspired by [Simon Willison's TIL](https://til.simonwillison.net/).",
        "",
        "## License",
        "",
        "This work is licensed under a [Creative Commons Attribution 4.0 International License](https://creativecommons.org/licenses/by/4.0/).",
    ])

    return "\n".join(lines)

generate_readme = generate_index  # Alias for backwards compat

if __name__ == "__main__":
    categories = build_index()
    index_content = generate_index(categories)

    index_path = WORKBENCH_DIR / "index.md"
    with open(index_path, 'w') as f:
        f.write(index_content)

    print(f"Updated {index_path}")
    print(f"Categories: {list(categories.keys())}")
    print(f"Total projects: {sum(len(e) for e in categories.values())}")
