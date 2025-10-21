import yaml
from typing import Dict, Any
from loguru import logger


def load_workflow_config(config_path: str) -> Dict[str, Any]:
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded workflow configuration from {config_path}")
        return config
    except Exception as e:
        logger.error(f"Failed to load config from {config_path}: {e}")
        raise


def validate_workflow_config(config_path: str) -> bool:
    try:
        config = load_workflow_config(config_path)
        if 'edges' not in config:
            logger.error("Missing required section: edges")
            return False
        
        for edge in config['edges']:
            if 'from' not in edge:
                logger.error("Edge missing required field: from")
                return False
            
            if 'conditional' in edge:
                cond = edge['conditional']
                if 'function' not in cond or 'branches' not in cond:
                    logger.error("Conditional edge missing required fields")
                    return False
        
        logger.info("Workflow configuration validation passed")
        return True
        
    except Exception as e:
        logger.error(f"Workflow config validation failed: {e}")
        return False