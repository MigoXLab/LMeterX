"""
Author: Charm
Copyright (c) 2025, All Rights Reserved.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from utils.common import is_url
from utils.dataset_loader import extract_prompt_from_conversations, normalize_image_path


def jsonl_to_sharegpt(input_file: str, output_file: str) -> None:
    """Convert JSONL format to ShareGPT JSON array format.

    Args:
        input_file: Path to input JSONL file
        output_file: Path to output JSON file
    """
    data: List[Dict[str, Any]] = []

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue

                try:
                    item = json.loads(line.strip())

                    # Build ShareGPT item
                    sharegpt_item: Dict[str, Any] = {}

                    # ID field
                    if "id" in item:
                        sharegpt_item["id"] = item["id"]

                    # Conversations field
                    if "prompt" in item:
                        sharegpt_item["conversations"] = [
                            {"from": "human", "value": item["prompt"]}
                        ]

                    # Image fields
                    if "image_url" in item:
                        sharegpt_item["image"] = item["image_url"]
                    elif "image_path" in item:
                        sharegpt_item["image"] = item["image_path"]
                    elif "image" in item:
                        sharegpt_item["image"] = item["image"]

                    # Image base64
                    if "image_base64" in item:
                        sharegpt_item["image_base64"] = item["image_base64"]

                    # Only add if has conversations
                    if "conversations" in sharegpt_item:
                        data.append(sharegpt_item)
                    else:
                        print(
                            f"Warning: Skipping line {line_num} - no prompt field",
                            file=sys.stderr,
                        )

                except json.JSONDecodeError as e:
                    print(f"Error parsing line {line_num}: {e}", file=sys.stderr)
                    continue

        # Write output
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(
            f"Successfully converted {len(data)} items from {input_file} to {output_file}"
        )

    except FileNotFoundError:
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        sys.exit(1)


def sharegpt_to_jsonl(input_file: str, output_file: str) -> None:
    """Convert ShareGPT JSON array format to JSONL format.

    Args:
        input_file: Path to input JSON file
        output_file: Path to output JSONL file
    """
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, list):
            print(f"Error: Expected JSON array in {input_file}", file=sys.stderr)
            sys.exit(1)

        converted_count = 0

        with open(output_file, "w", encoding="utf-8") as f:
            for idx, item in enumerate(data, 1):
                if not isinstance(item, dict):
                    print(
                        f"Warning: Skipping non-dict item at index {idx}",
                        file=sys.stderr,
                    )
                    continue

                # Build JSONL item
                jsonl_item: Dict[str, Any] = {}

                # ID field
                if "id" in item:
                    jsonl_item["id"] = item["id"]

                # Extract prompt from conversations
                if "prompt" in item:
                    # Direct prompt field
                    jsonl_item["prompt"] = item["prompt"]
                elif "conversations" in item:
                    # Extract from conversations using utility function
                    prompt = extract_prompt_from_conversations(item["conversations"])
                    if prompt:
                        jsonl_item["prompt"] = prompt

                # Image fields
                if "image" in item:
                    image_value = normalize_image_path(item["image"])
                    if image_value:
                        # Check if it's a URL
                        if is_url(image_value):
                            jsonl_item["image_url"] = image_value
                        else:
                            jsonl_item["image_path"] = image_value

                if "image_base64" in item:
                    jsonl_item["image_base64"] = item["image_base64"]

                # Only add if has prompt
                if "prompt" in jsonl_item:
                    f.write(json.dumps(jsonl_item, ensure_ascii=False) + "\n")
                    converted_count += 1
                else:
                    print(
                        f"Warning: Skipping item {idx} - no valid prompt found",
                        file=sys.stderr,
                    )

        print(
            f"Successfully converted {converted_count} items from {input_file} to {output_file}"
        )

    except FileNotFoundError:
        print(f"Error: Input file not found: {input_file}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error during conversion: {e}", file=sys.stderr)
        sys.exit(1)


def detect_format(file_path: str) -> str:
    """Detect file format (jsonl or json).

    Args:
        file_path: Path to the file

    Returns:
        'jsonl' or 'json'
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content.startswith("["):
                return "json"
            else:
                return "jsonl"
    except Exception:
        # Default to jsonl
        return "jsonl"


def main():
    """Main entry point for the converter CLI."""
    parser = argparse.ArgumentParser(
        description="Convert between JSONL and ShareGPT JSON array formats",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Convert JSONL to ShareGPT JSON format
  python dataset_converter.py input.jsonl output.json --to-sharegpt

  # Convert ShareGPT JSON to JSONL format
  python dataset_converter.py input.json output.jsonl --to-jsonl

  # Auto-detect format and convert
  python dataset_converter.py input.jsonl output.json
        """,
    )

    parser.add_argument("input_file", help="Input file path")
    parser.add_argument("output_file", help="Output file path")
    parser.add_argument(
        "--to-sharegpt", action="store_true", help="Convert to ShareGPT JSON format"
    )
    parser.add_argument(
        "--to-jsonl", action="store_true", help="Convert to JSONL format"
    )

    args = parser.parse_args()

    # Validate input file exists
    if not Path(args.input_file).exists():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    # Determine conversion direction
    if args.to_sharegpt and args.to_jsonl:
        print(
            "Error: Cannot specify both --to-sharegpt and --to-jsonl", file=sys.stderr
        )
        sys.exit(1)

    if args.to_sharegpt:
        print(
            f"Converting {args.input_file} (JSONL) -> {args.output_file} (ShareGPT JSON)"
        )
        jsonl_to_sharegpt(args.input_file, args.output_file)
    elif args.to_jsonl:
        print(
            f"Converting {args.input_file} (ShareGPT JSON) -> {args.output_file} (JSONL)"
        )
        sharegpt_to_jsonl(args.input_file, args.output_file)
    else:
        # Auto-detect format
        input_format = detect_format(args.input_file)
        print(f"Detected input format: {input_format.upper()}")

        if input_format == "jsonl":
            print(
                f"Converting {args.input_file} (JSONL) -> {args.output_file} (ShareGPT JSON)"
            )
            jsonl_to_sharegpt(args.input_file, args.output_file)
        else:
            print(
                f"Converting {args.input_file} (ShareGPT JSON) -> {args.output_file} (JSONL)"
            )
            sharegpt_to_jsonl(args.input_file, args.output_file)


if __name__ == "__main__":
    main()
