import yaml
import os
from functools import lru_cache

@lru_cache(maxsize=1)
def load_config():
    """
    Load and cache configuration from config.yaml.
    Cached using lru_cache to avoid reloading the file multiple times.
    """
    try:
        config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
        config_path = os.path.abspath(config_path)

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found at: {config_path}")

        with open(config_path, "r") as file:
            config = yaml.safe_load(file)

        return config
    except Exception as e:
        raise RuntimeError(f"Error loading configuration: {e}")



def remove_nulls(data):
    """
    Recursively removes any key-value pairs where value is None (null in JSON).
    Works for nested dicts and lists.
    """
    # If not a dict → return unchanged
    if not isinstance(data, dict):
        return data  
        
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():

            # Skip any null value
            if value is None:
                continue  

            # Recursively clean nested structure
            cleaned_value = remove_nulls(value)

            # Only keep if not empty after cleaning
            if cleaned_value != {} and cleaned_value != []:
                cleaned[key] = cleaned_value

        return cleaned

    elif isinstance(data, list):
        cleaned_list = [remove_nulls(item) for item in data]
        return [item for item in cleaned_list if item not in ({}, None)]

    else:
        return data
