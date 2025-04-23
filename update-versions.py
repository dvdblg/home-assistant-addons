import os
import yaml
import requests
import logging
from packaging import version
import argparse
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def get_latest_tag(repo_name):
    """
    Get the latest semantic version tag from Docker Hub.
    Only fetches a small number of the latest tags for efficiency.
    """
    # Use page size and page limit to restrict to only recent tags
    page_size = 20  # Fetch only 20 tags at a time
    max_pages = 1   # Only check the first page by default
    
    tags_url = f'https://hub.docker.com/v2/repositories/{repo_name}/tags?page_size={page_size}'
    all_tags = []
    current_page = 0
    
    while tags_url and current_page < max_pages:
        try:
            response = requests.get(tags_url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Extract tags from current page
            results = data.get('results', [])
            all_tags.extend([tag['name'] for tag in results if any(char.isdigit() for char in tag['name'])])
            
            # Get URL for next page or None if no more pages
            tags_url = data.get('next')
            current_page += 1
            
            # If we don't have enough tags yet, check one more page
            if len(all_tags) < 5 and tags_url:
                max_pages += 1
        except requests.RequestException as e:
            logger.error(f"Error fetching tags for {repo_name}: {e}")
            return None
    
    logger.debug(f"Found {len(all_tags)} tags for {repo_name}")
    
    # Filter and sort version tags
    try:
        # Try to sort using semantic versioning
        valid_tags = []
        for tag in all_tags:
            try:
                parsed_version = version.parse(tag)
                if not isinstance(parsed_version, version.LegacyVersion):
                    valid_tags.append((parsed_version, tag))
            except (TypeError, ValueError):
                continue
        
        if valid_tags:
            valid_tags.sort(reverse=True)
            return valid_tags[0][1]
        else:
            # Fallback to simple string sorting
            logger.warning(f"No proper semantic versions found for {repo_name}, using string sorting")
            return sorted(all_tags, reverse=True)[0] if all_tags else None
    except Exception as e:
        logger.error(f"Error sorting tags for {repo_name}: {e}")
        return None

def update_config_files(directory='.'):
    """
    Update version in config.yaml files by walking through the directory.
    """
    updated_count = 0
    error_count = 0
    
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file == 'config.yaml':
                file_path = os.path.join(root, file)
                try:
                    with open(file_path, 'r') as f:
                        # Use yaml.safe_load to parse the YAML file
                        config = yaml.safe_load(f)
                    
                    if not isinstance(config, dict):
                        logger.warning(f"Skipping {file_path}: Not a valid YAML dictionary")
                        continue
                    
                    if 'image' in config:
                        logger.info(f'Processing {file_path} with image {config["image"]}')
                        latest_tag = get_latest_tag(config['image'])
                        
                        if latest_tag:
                            logger.info(f'Latest version of {config["image"]} is {latest_tag}')
                            current_version = config.get('version')
                            
                            if current_version != latest_tag:
                                logger.info(f'Updating {file_path} from {current_version} to {latest_tag}')
                                config['version'] = latest_tag
                                
                                # Preserve the original format and comments when writing back
                                with open(file_path, 'w') as f:
                                    yaml.dump(config, f, default_flow_style=False, sort_keys=False)
                                updated_count += 1
                            else:
                                logger.info(f'{file_path} already at latest version {current_version}')
                        else:
                            logger.warning(f'Could not determine latest version for {config["image"]}')
                except Exception as e:
                    logger.error(f"Error processing {file_path}: {e}")
                    error_count += 1
    
    return updated_count, error_count

if __name__ == "__main__":
    try:
        # Set up argument parser
        parser = argparse.ArgumentParser(
            description='Update version in config.yaml files with latest Docker Hub tags.'
        )
        parser.add_argument(
            '-d', '--directory', 
            default='.', 
            help='Directory to search for config.yaml files (default: current directory)'
        )
        parser.add_argument(
            '-v', '--verbose', 
            action='store_true', 
            help='Enable verbose output'
        )
        
        # Parse arguments
        args = parser.parse_args()
        
        # Set log level based on verbosity
        if args.verbose:
            logger.setLevel(logging.DEBUG)
            
        logger.info(f"Starting update process in directory: {args.directory}")
        updated, errors = update_config_files(args.directory)
        logger.info(f"Process completed. Updated {updated} files with {errors} errors.")
    except KeyboardInterrupt:
        logger.info("Process interrupted by user.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
