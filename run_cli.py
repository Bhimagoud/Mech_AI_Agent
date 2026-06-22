"""
CLI Runner — Test the pipeline without starting the Flask server.

Usage:
    python run_cli.py --sar path/to/SAR.docx [--manual path/to/NBA_Manual.pdf]

Or use sample built-in data:
    python run_cli.py --sample
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from orchestrator import run_pipeline


SAMPLE_PEOS = [
    {"id": "PEO1", "text": "Develop, design, implement, and maintain technically robust, economically viable, and socially responsible Mechanical Engineering systems, products, and processes."},
    {"id": "PEO2", "text": "Apply analytical, computational, and experimental methods to investigate and resolve complex challenges in mechanical and allied engineering domains."},
    {"id": "PEO3", "text": "Communicate complex engineering findings effectively using diverse technical communication channels and modern digital tools."},
    {"id": "PEO4", "text": "Demonstrate strong collaboration, professional networking, and entrepreneurial aptitude in diverse engineering environments."},
    {"id": "PEO5", "text": "Exhibit professionalism, ethical conduct, and teamwork while committing to continuous learning to achieve career, organisational, and societal objectives."},
]

SAMPLE_DMS = [
    {"id": "DM1", "text": "Prepare industry-ready graduates through quality, outcome-based education that enhances both cognitive and non-cognitive professional competencies."},
    {"id": "DM2", "text": "Cultivate a thriving academic and research ecosystem to achieve the highest levels of engineering competency and innovation."},
    {"id": "DM3", "text": "Impart and facilitate state-of-the-art, multidisciplinary education to develop research capability and address complex engineering challenges."},
]


def main():
    parser = argparse.ArgumentParser(description="NBA PEO–Mission Mapping CLI")
    parser.add_argument("--sar",    help="Path to SAR PDF or DOCX file")
    parser.add_argument("--manual", help="Path to NBA manual PDF (optional)")
    parser.add_argument("--sample", action="store_true", help="Use built-in sample data")
    parser.add_argument("--output", help="Path to save JSON output", default="output.json")
    args = parser.parse_args()

    if args.sample:
        print("▶ Running pipeline with sample data...")
        result = run_pipeline(
            sar_bytes=b"sample",
            sar_filename="sample_sar.txt",
            extra_peos=SAMPLE_PEOS,
            extra_missions=SAMPLE_DMS,
        )
    elif args.sar:
        with open(args.sar, "rb") as f:
            sar_bytes = f.read()
        manual_bytes = None
        if args.manual:
            with open(args.manual, "rb") as f:
                manual_bytes = f.read()

        print(f"▶ Running pipeline on: {args.sar}")
        result = run_pipeline(
            sar_bytes=sar_bytes,
            sar_filename=os.path.basename(args.sar),
            manual_bytes=manual_bytes,
            manual_filename=os.path.basename(args.manual) if args.manual else "",
        )
    else:
        parser.print_help()
        sys.exit(1)

    if result["status"] == "error":
        print(f"\n❌ Pipeline failed: {result['error']}")
        sys.exit(1)

    print("\n✅ Pipeline completed successfully!\n")

    # Print markdown report to stdout
    print("=" * 70)
    print(result["report"]["markdown"])
    print("=" * 70)

    # Save full JSON
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n📁 Full JSON output saved to: {args.output}")


if __name__ == "__main__":
    main()
