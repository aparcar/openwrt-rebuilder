import json
import os
import shutil
from pathlib import Path
from datetime import datetime

# Collect all output.json files
combined_data = {}
artifacts_path = Path("results")

for results_dir in artifacts_path.glob("results-*"):
    output_json_path = results_dir / "output.json"
    if output_json_path.exists():
        print(f"Processing {output_json_path}")
        with open(output_json_path) as f:
            data = json.load(f)
            # Merge the data
            for version, version_data in data.items():
                if version not in combined_data:
                    combined_data[version] = {}
                combined_data[version].update(version_data)

        # Copy diffoscope HTML files
        diffoscope_files = list(results_dir.glob("**/*.html"))
        for html_file in diffoscope_files:
            if html_file.name != "index.html":  # Skip any existing index files
                dest_path = Path("combined_results/diffoscope") / html_file.name
                print(f"Copying {html_file} to {dest_path}")
                shutil.copy2(html_file, dest_path)

# Write combined results
with open("combined_results/output.json", "w") as f:
    json.dump(combined_data, f, indent=2)

# Build metadata
build_time = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
github_sha = os.environ.get("GITHUB_SHA", "unknown")[:8]
github_ref = os.environ.get("GITHUB_REF_NAME", "unknown")
github_run_id = os.environ.get("GITHUB_RUN_ID", "unknown")

def generate_target_page(version, target, target_data, release_dir):
    """Generate detailed page for a specific target"""
    target_slug = target.replace('/', '_')
    os.makedirs(f"combined_results/{release_dir}", exist_ok=True)

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{target} - {version} - OpenWrt Reproducible Build Results</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
            .breadcrumb {{ margin-bottom: 20px; }}
            .breadcrumb a {{ color: #3498db; text-decoration: none; }}
            .breadcrumb a:hover {{ text-decoration: underline; }}
            .category {{ background: #f8f9fa; border: 1px solid #dee2e6; border-radius: 5px; margin: 15px 0; }}
            .category-header {{ background: #e9ecef; padding: 15px; font-weight: bold; font-size: 1.2em; }}
            .status-section {{ margin: 10px 0; }}
            .status-header {{ padding: 10px 15px; font-weight: bold; margin: 10px 0; border-radius: 3px; }}
            .status-header.reproducible {{ background: #d4edda; color: #155724; }}
            .status-header.unreproducible {{ background: #f8d7da; color: #721c24; }}
            .status-header.notfound {{ background: #fff3cd; color: #856404; }}
            .status-header.pending {{ background: #d1ecf1; color: #0c5460; }}
            .item {{ margin: 8px 0; padding: 12px; background: white; border-left: 4px solid #ddd; border-radius: 3px; }}
            .item.reproducible {{ border-left-color: #28a745; }}
            .item.unreproducible {{ border-left-color: #dc3545; }}
            .item.notfound {{ border-left-color: #ffc107; }}
            .item.pending {{ border-left-color: #17a2b8; }}
            .item-name {{ font-weight: bold; margin-bottom: 5px; }}
            .item-details {{ font-size: 0.9em; color: #666; }}
            .diffoscope-link {{ margin-top: 8px; }}
            .diffoscope-link a {{ background: #007bff; color: white; padding: 4px 8px; border-radius: 3px; text-decoration: none; font-size: 0.85em; }}
            .diffoscope-link a:hover {{ background: #0056b3; }}
            .summary-box {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin: 15px 0; }}
            .stats-inline {{ display: inline-block; margin-right: 20px; }}
        </style>
    </head>
    <body>
        <div class="breadcrumb">
            <a href="../index.html">← All Releases</a> /
            <a href="../{release_dir}.html">{version}</a> /
            {target}
        </div>

        <div class="header">
            <h1>{target}</h1>
            <h2>Version: {version}</h2>
        </div>
    """

    # Calculate stats for this target
    target_stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}

    for category in ["packages", "images"]:
        if category in target_data:
            for status in target_stats.keys():
                target_stats[status] += len(target_data[category].get(status, []))

    total_items = sum(target_stats.values())
    reproducible_percent = (target_stats['reproducible'] / total_items * 100) if total_items > 0 else 0

    html_content += f"""
        <div class="summary-box">
            <h3>Target Summary</h3>
            <div>
                <span class="stats-inline"><strong style="color: #28a745;">Reproducible:</strong> {target_stats['reproducible']}</span>
                <span class="stats-inline"><strong style="color: #dc3545;">Unreproducible:</strong> {target_stats['unreproducible']}</span>
                <span class="stats-inline"><strong style="color: #ffc107;">Not Found:</strong> {target_stats['notfound']}</span>
                <span class="stats-inline"><strong style="color: #17a2b8;">Pending:</strong> {target_stats['pending']}</span>
            </div>
            <p><strong>{reproducible_percent:.1f}% Reproducible</strong> ({target_stats['reproducible']} of {total_items} items)</p>
        </div>
    """

    # Generate detailed sections for each category
    for category in ["images", "packages"]:
        if category not in target_data:
            continue

        html_content += f"""
        <div class="category">
            <div class="category-header">{category.title()}</div>
        """

        for status in ["reproducible", "unreproducible", "notfound", "pending"]:
            items = target_data[category].get(status, [])
            if not items:
                continue

            html_content += f"""
            <div class="status-section">
                <div class="status-header {status}">{status.title()} ({len(items)})</div>
            """

            for item in items:
                html_content += f"""
                <div class="item {status}">
                    <div class="item-name">{item['name']}</div>
                    <div class="item-details">
                        Architecture: {item.get('arch', 'N/A')} |
                        Version: {item.get('version', 'N/A')}
                """

                if item.get('files'):
                    for file_status, files in item['files'].items():
                        html_content += f"<br>Files ({file_status}): {', '.join(files)}"

                html_content += "</div>"

                if item.get("diffoscope"):
                    html_content += f"""
                    <div class="diffoscope-link">
                        <a href="../diffoscope/{item['diffoscope']}" target="_blank">View Diffoscope Analysis</a>
                    </div>
                    """

                html_content += "</div>"

            html_content += "</div>"

        html_content += "</div>"

    html_content += """
    </body>
    </html>
    """

    with open(f"combined_results/{release_dir}/{target_slug}.html", "w") as f:
        f.write(html_content)

    return target_stats

def generate_release_page(version, targets_data):
    """Generate release overview page with all targets for this version"""
    release_dir = version.replace('.', '_')

    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{version} - OpenWrt Reproducible Build Results</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
            .breadcrumb {{ margin-bottom: 20px; }}
            .breadcrumb a {{ color: #3498db; text-decoration: none; }}
            .breadcrumb a:hover {{ text-decoration: underline; }}
            .targets-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin: 20px 0; }}
            .target-card {{ background: white; border: 1px solid #ddd; border-radius: 8px; padding: 20px; transition: all 0.2s; }}
            .target-card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.15); transform: translateY(-2px); }}
            .target-name {{ font-weight: bold; font-size: 1.2em; margin-bottom: 15px; }}
            .target-name a {{ color: #2c3e50; text-decoration: none; }}
            .target-name a:hover {{ color: #3498db; }}
            .progress-bar {{ background: #e0e0e0; border-radius: 10px; height: 12px; margin: 10px 0; }}
            .progress-fill {{ height: 100%; border-radius: 10px; background: linear-gradient(to right, #28a745, #20c997); }}
            .stats-row {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 15px 0; }}
            .stat {{ text-align: center; padding: 8px; border-radius: 5px; }}
            .stat-value {{ font-weight: bold; font-size: 1.1em; }}
            .stat-label {{ font-size: 0.85em; margin-top: 2px; }}
            .stat-reproducible {{ background: #d4edda; color: #155724; }}
            .stat-unreproducible {{ background: #f8d7da; color: #721c24; }}
            .stat-notfound {{ background: #fff3cd; color: #856404; }}
            .stat-pending {{ background: #d1ecf1; color: #0c5460; }}
            .version-summary {{ background: #e8f4fd; border: 1px solid #bee5eb; border-radius: 8px; padding: 25px; margin: 25px 0; }}
        </style>
    </head>
    <body>
        <div class="breadcrumb">
            <a href="../index.html">← All Releases</a>
        </div>

        <div class="header">
            <h1>OpenWrt {version}</h1>
            <p>Reproducible Build Results</p>
        </div>
    """

    version_stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}

    html_content += '<div class="targets-grid">'

    for target, target_data in targets_data.items():
        target_slug = target.replace('/', '_')

        # Generate target page and get stats
        target_stats = generate_target_page(version, target, target_data, release_dir)

        # Accumulate version stats
        for status in version_stats.keys():
            version_stats[status] += target_stats[status]

        total_target_items = sum(target_stats.values())
        target_reproducible_percent = (target_stats['reproducible'] / total_target_items * 100) if total_target_items > 0 else 0

        html_content += f"""
        <div class="target-card">
            <div class="target-name">
                <a href="{release_dir}/{target_slug}.html">{target}</a>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {target_reproducible_percent:.1f}%"></div>
            </div>
            <div style="text-align: center; margin: 12px 0; font-weight: bold; font-size: 1.1em;">
                {target_reproducible_percent:.1f}% Reproducible
            </div>
            <div class="stats-row">
                <div class="stat stat-reproducible">
                    <div class="stat-value">{target_stats['reproducible']}</div>
                    <div class="stat-label">Reproducible</div>
                </div>
                <div class="stat stat-unreproducible">
                    <div class="stat-value">{target_stats['unreproducible']}</div>
                    <div class="stat-label">Unreproducible</div>
                </div>
                <div class="stat stat-notfound">
                    <div class="stat-value">{target_stats['notfound']}</div>
                    <div class="stat-label">Not Found</div>
                </div>
                <div class="stat stat-pending">
                    <div class="stat-value">{target_stats['pending']}</div>
                    <div class="stat-label">Pending</div>
                </div>
            </div>
        </div>
        """

    html_content += '</div>'

    # Version summary
    total_version_items = sum(version_stats.values())
    version_reproducible_percent = (version_stats['reproducible'] / total_version_items * 100) if total_version_items > 0 else 0

    html_content += f"""
    <div class="version-summary">
        <h2>{version} Overall Summary</h2>
        <div style="text-align: center; font-size: 1.4em; font-weight: bold; margin: 15px 0;">
            {version_reproducible_percent:.1f}% Reproducible ({version_stats['reproducible']} of {total_version_items} items)
        </div>
        <div class="stats-row" style="max-width: 600px; margin: 0 auto;">
            <div class="stat stat-reproducible">
                <div class="stat-value">{version_stats['reproducible']}</div>
                <div class="stat-label">Reproducible</div>
            </div>
            <div class="stat stat-unreproducible">
                <div class="stat-value">{version_stats['unreproducible']}</div>
                <div class="stat-label">Unreproducible</div>
            </div>
            <div class="stat stat-notfound">
                <div class="stat-value">{version_stats['notfound']}</div>
                <div class="stat-label">Not Found</div>
            </div>
            <div class="stat stat-pending">
                <div class="stat-value">{version_stats['pending']}</div>
                <div class="stat-label">Pending</div>
            </div>
        </div>
    </div>
    </body>
    </html>
    """

    with open(f"combined_results/{release_dir}.html", "w") as f:
        f.write(html_content)

    return version_stats

# Generate main index page with release cards
html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenWrt Reproducible Build Results</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; }}
        .header {{ background: #2c3e50; color: white; padding: 25px; border-radius: 8px; margin-bottom: 30px; }}
        .build-info {{ font-size: 0.9em; margin-top: 15px; opacity: 0.9; }}
        .releases-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 25px; margin: 30px 0; }}
        .release-card {{ background: white; border: 1px solid #ddd; border-radius: 10px; padding: 25px; transition: all 0.3s; }}
        .release-card:hover {{ box-shadow: 0 6px 20px rgba(0,0,0,0.15); transform: translateY(-3px); }}
        .release-name {{ font-weight: bold; font-size: 1.4em; margin-bottom: 15px; }}
        .release-name a {{ color: #2c3e50; text-decoration: none; }}
        .release-name a:hover {{ color: #3498db; }}
        .progress-bar {{ background: #e0e0e0; border-radius: 12px; height: 16px; margin: 15px 0; }}
        .progress-fill {{ height: 100%; border-radius: 12px; background: linear-gradient(to right, #28a745, #20c997); }}
        .release-stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }}
        .stat-box {{ text-align: center; padding: 12px; border-radius: 6px; }}
        .stat-value {{ font-weight: bold; font-size: 1.2em; }}
        .stat-label {{ font-size: 0.9em; margin-top: 3px; }}
        .stat-reproducible {{ background: #d4edda; color: #155724; }}
        .stat-unreproducible {{ background: #f8d7da; color: #721c24; }}
        .target-count {{ text-align: center; margin-top: 15px; font-size: 0.95em; color: #666; }}
        .overall-summary {{ background: #e8f4fd; border: 1px solid #bee5eb; border-radius: 10px; padding: 30px; margin: 40px 0; text-align: center; }}
        .footer {{ margin-top: 40px; padding: 20px; background: #f8f9fa; border-radius: 8px; font-size: 0.9em; color: #666; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>OpenWrt Reproducible Build Results</h1>
        <p>Compare reproducibility across releases and targets</p>
        <div class="build-info">
            <strong>Build Time:</strong> {build_time} |
            <strong>Commit:</strong> {github_sha} |
            <strong>Branch:</strong> {github_ref} |
            <strong>Run:</strong> {github_run_id}
        </div>
    </div>

    <div class="releases-grid">
"""

overall_stats = {"reproducible": 0, "unreproducible": 0, "notfound": 0, "pending": 0}

# Generate release pages and cards
for version, targets_data in combined_data.items():
    version_stats = generate_release_page(version, targets_data)

    # Accumulate overall stats
    for status in overall_stats.keys():
        overall_stats[status] += version_stats[status]

    total_version_items = sum(version_stats.values())
    version_reproducible_percent = (version_stats['reproducible'] / total_version_items * 100) if total_version_items > 0 else 0
    release_file = f"{version.replace('.', '_')}.html"
    target_count = len(targets_data)

    html_content += f"""
        <div class="release-card">
            <div class="release-name">
                <a href="{release_file}">OpenWrt {version}</a>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {version_reproducible_percent:.1f}%"></div>
            </div>
            <div style="text-align: center; font-size: 1.3em; font-weight: bold; margin: 15px 0;">
                {version_reproducible_percent:.1f}% Reproducible
            </div>
            <div class="release-stats">
                <div class="stat-box stat-reproducible">
                    <div class="stat-value">{version_stats['reproducible']}</div>
                    <div class="stat-label">Reproducible</div>
                </div>
                <div class="stat-box stat-unreproducible">
                    <div class="stat-value">{version_stats['unreproducible']}</div>
                    <div class="stat-label">Unreproducible</div>
                </div>
            </div>
            <div class="target-count">
                {target_count} target{'s' if target_count != 1 else ''} tested
            </div>
        </div>
    """

# Overall summary
total_all_items = sum(overall_stats.values())
overall_reproducible_percent = (overall_stats['reproducible'] / total_all_items * 100) if total_all_items > 0 else 0

html_content += f"""
    </div>

    <div class="overall-summary">
        <h2>Overall Summary Across All Releases</h2>
        <div style="font-size: 1.5em; font-weight: bold; margin: 20px 0;">
            {overall_reproducible_percent:.1f}% Reproducible
        </div>
        <div style="font-size: 1.1em; margin: 10px 0;">
            {overall_stats['reproducible']} of {total_all_items} items are reproducible
        </div>
        <div style="margin-top: 20px;">
            <span style="color: #28a745; margin: 0 15px;"><strong>{overall_stats['reproducible']}</strong> Reproducible</span>
            <span style="color: #dc3545; margin: 0 15px;"><strong>{overall_stats['unreproducible']}</strong> Unreproducible</span>
            <span style="color: #ffc107; margin: 0 15px;"><strong>{overall_stats['notfound']}</strong> Not Found</span>
            <span style="color: #17a2b8; margin: 0 15px;"><strong>{overall_stats['pending']}</strong> Pending</span>
        </div>
    </div>

    <div class="footer">
        <p><strong>About Reproducible Builds:</strong> Reproducible builds enable verification that no vulnerabilities or backdoors have been introduced during compilation by allowing independent verification of build outputs.</p>
        <p>Generated by OpenWrt Reproducible Build CI | <a href="https://reproducible-builds.org/">Learn more about reproducible builds</a></p>
    </div>
</body>
</html>
"""

with open("combined_results/index.html", "w") as f:
    f.write(html_content)

# Count generated files
release_pages = len([f for f in Path('combined_results').glob('*.html') if f.name != 'index.html'])
target_pages = sum(len(list(Path('combined_results').glob(f'{release.replace(".", "_")}/*.html'))) for release in combined_data.keys())
diffoscope_files = len(list(Path('combined_results/diffoscope').glob('*.html')))

print("Generated fully hierarchical overview:")
print(f"- combined_results/index.html (main overview)")
print(f"- {release_pages} release pages")
print(f"- {target_pages} target detail pages")
print(f"- {diffoscope_files} diffoscope reports")
print(f"- combined_results/output.json (combined data)")
