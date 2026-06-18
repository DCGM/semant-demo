#!/usr/bin/env python3
"""
Merge JSONL files from multiple directories, checking for conflicts and combining keys.
"""

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from collections import defaultdict


logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def load_jsonl(file_path: Path) -> List[Dict]:
    """Load records from a JSONL file."""
    records = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in {file_path} at line {line_num}: {e}")
                raise
    return records


def save_jsonl(file_path: Path, records: List[Dict]):
    """Save records to a JSONL file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def rename_key_in_records(records: List[Dict], old_key: str, new_key: str) -> List[Dict]:
    """Rename a key in all records."""
    renamed_records = []
    for record in records:
        if old_key in record:
            record = record.copy()
            record[new_key] = record.pop(old_key)
        renamed_records.append(record)
    return renamed_records


def get_all_jsonl_files(directories: List[Path]) -> Set[str]:
    """Get all unique JSONL file names from all directories."""
    all_files = set()
    for directory in directories:
        if not directory.exists():
            logger.error(f"Directory does not exist: {directory}")
            sys.exit(1)
        for file_path in directory.glob('*.jsonl'):
            all_files.add(file_path.name)
    return all_files


def merge_records(
    file_name: str,
    directories: List[Path],
    rename_keys: Optional[Dict[str, str]] = None
) -> Tuple[List[Dict], bool]:
    """
    Merge records from the same file across multiple directories.
    
    Returns:
        Tuple of (merged_records, has_errors)
    """
    if rename_keys is None:
        rename_keys = {}
    
    has_errors = False
    
    # Check if file exists in all directories
    file_paths = []
    for directory in directories:
        file_path = directory / file_name
        if not file_path.exists():
            logger.error(f"File {file_name} not found in directory: {directory}")
            continue
        file_paths.append(file_path)
    
    # Load records from all directories, organizing by record ID
    records_by_id: Dict[str, List[Dict]] = defaultdict(list)
    directory_indices: Dict[str, List[int]] = defaultdict(list)
    
    for dir_idx, file_path in enumerate(file_paths):
        records = load_jsonl(file_path)
         
        # Apply key renaming
        if rename_keys:
            for old_key, new_key in rename_keys.items():
                records = rename_key_in_records(records, old_key, new_key)
        
        for record in records:
            if 'id' not in record:
                logger.error(f"Record without 'id' field in {file_path}")
                continue
            
            record_id = record['id']
            records_by_id[record_id].append(record)
            directory_indices[record_id].append(dir_idx)
    
    # Merge records and check for conflicts
    merged_records = []
    
    for record_id, record_versions in records_by_id.items():
        if len(record_versions) != len(directories):
            missing_dirs = set(range(len(directories))) - set(directory_indices[record_id])
            missing_names = [str(directories[i]) for i in missing_dirs]
            logger.error(
                f"Record {record_id} in {file_name} not found in all directories. "
                f"Missing from: {', '.join(missing_names)}"
            )
        
        # Merge all keys from all versions
        merged_record = {}
        all_keys = set()
        for record in record_versions:
            all_keys.update(record.keys())
        
        for key in all_keys:
            values = []
            for record in record_versions:
                if key in record:
                    values.append(record[key])
            
            # Check if all values are the same
            if len(set(json.dumps(v, sort_keys=True) for v in values)) > 1:
                logger.error(
                    f"Conflict in {file_name}, record {record_id}, key '{key}': "
                    f"different values found: {values}"
                )
                # Use the first value as default
                merged_record[key] = values[0]
            else:
                # All values are the same or key only exists in some records
                merged_record[key] = values[0]
        
        merged_records.append(merged_record)
    
    # Sort by 'order' field
    if merged_records and 'order' in merged_records[0]:
        merged_records.sort(key=lambda x: x.get('order', 0))
    else:
        logger.warning(f"No 'order' field found in {file_name}, skipping sorting")
    
    return merged_records, has_errors


def main():
    parser = argparse.ArgumentParser(
        description='Merge JSONL files from multiple directories with conflict detection.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Merge files from two directories
  %(prog)s dir1 dir2 -o output_dir
  
  # Merge with key renaming
  %(prog)s dir1 dir2 -o output_dir --rename old_name=new_name
  
  # Multiple key renames
  %(prog)s dir1 dir2 -o output_dir --rename key1=new1 --rename key2=new2
        """
    )
    
    parser.add_argument(
        'directories',
        nargs='+',
        type=Path,
        help='Input directories containing JSONL files'
    )
    
    parser.add_argument(
        '-o', '--output',
        type=Path,
        required=True,
        help='Output directory for merged JSONL files'
    )
    
    parser.add_argument(
        '--rename',
        action='append',
        dest='renames',
        metavar='OLD=NEW',
        help='Rename a key before merging (can be specified multiple times)'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    # Parse key renames
    rename_keys = {}
    if args.renames:
        for rename_spec in args.renames:
            if '=' not in rename_spec:
                logger.error(f"Invalid rename specification: {rename_spec}. Use format: OLD=NEW")
                sys.exit(1)
            old_key, new_key = rename_spec.split('=', 1)
            rename_keys[old_key.strip()] = new_key.strip()
        logger.info(f"Key renames: {rename_keys}")
    
    # Get all JSONL files
    all_files = get_all_jsonl_files(args.directories)
    logger.info(f"Found {len(all_files)} unique JSONL files")
    
    # Process each file
    total_errors = 0
    successful_merges = 0
    
    for file_name in sorted(all_files):
        logger.info(f"Processing {file_name}...")
        merged_records, has_errors = merge_records(
            file_name,
            args.directories,
            rename_keys
        )
        
        if has_errors:
            total_errors += 1
        
        if merged_records:
            output_path = args.output / file_name
            save_jsonl(output_path, merged_records)
            logger.info(f"Saved {len(merged_records)} records to {output_path}")
            successful_merges += 1
    
    # Summary
    logger.info(f"\nMerge complete:")
    logger.info(f"  Successfully merged: {successful_merges} files")
    logger.info(f"  Files with errors: {total_errors}")
    
    if total_errors > 0:
        logger.warning("Some files had errors. Please review the log messages above.")
        sys.exit(1)


if __name__ == '__main__':
    main()
