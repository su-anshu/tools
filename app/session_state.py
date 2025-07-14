"""
Session State Management for Mithila Tools Dashboard

This module provides utilities for managing Streamlit session state,
ensuring data persistence across reruns and improving user experience.
"""

import streamlit as st
import pandas as pd
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

class SessionStateManager:
    """Manages session state for the Mithila Tools Dashboard"""
    
    def __init__(self):
        """Initialize session state with default values"""
        self._initialize_session_state()
    
    def _initialize_session_state(self):
        """Initialize all session state variables with default values"""
        
        # File upload states
        if 'uploaded_files' not in st.session_state:
            st.session_state.uploaded_files = {}
        
        if 'processed_data' not in st.session_state:
            st.session_state.processed_data = {}
        
        # Master data state
        if 'master_df' not in st.session_state:
            st.session_state.master_df = None
        
        if 'master_data_timestamp' not in st.session_state:
            st.session_state.master_data_timestamp = None
        
        # Configuration states
        if 'google_sheet_url' not in st.session_state:
            st.session_state.google_sheet_url = ""
        
        if 'admin_authenticated' not in st.session_state:
            st.session_state.admin_authenticated = False
        
        # Processing states
        if 'last_processing_result' not in st.session_state:
            st.session_state.last_processing_result = None
        
        if 'current_tool' not in st.session_state:
            st.session_state.current_tool = "📦 Packing Plan Generator"
        
        # Cache for expensive operations
        if 'cached_calculations' not in st.session_state:
            st.session_state.cached_calculations = {}
    
    def store_uploaded_file(self, key: str, file_data: bytes, filename: str, file_type: str):
        """Store uploaded file data in session state"""
        try:
            st.session_state.uploaded_files[key] = {
                'data': file_data,
                'filename': filename,
                'type': file_type,
                'size': len(file_data)
            }
            logger.info(f"Stored uploaded file: {filename} ({len(file_data)} bytes)")
        except Exception as e:
            logger.error(f"Error storing uploaded file {filename}: {str(e)}")
    
    def get_uploaded_file(self, key: str) -> Optional[Dict]:
        """Retrieve uploaded file data from session state"""
        return st.session_state.uploaded_files.get(key)
    
    def store_processed_data(self, key: str, data: Any):
        """Store processed data results in session state"""
        try:
            st.session_state.processed_data[key] = data
            logger.info(f"Stored processed data: {key}")
        except Exception as e:
            logger.error(f"Error storing processed data {key}: {str(e)}")
    
    def get_processed_data(self, key: str) -> Any:
        """Retrieve processed data from session state"""
        return st.session_state.processed_data.get(key)
    
    def store_master_data(self, df: pd.DataFrame, timestamp: str = None):
        """Store master DataFrame in session state"""
        try:
            st.session_state.master_df = df.copy()
            st.session_state.master_data_timestamp = timestamp
            logger.info(f"Stored master data: {len(df)} rows")
        except Exception as e:
            logger.error(f"Error storing master data: {str(e)}")
    
    def get_master_data(self) -> Optional[pd.DataFrame]:
        """Retrieve master DataFrame from session state"""
        return st.session_state.master_df
    
    def store_config(self, key: str, value: Any):
        """Store configuration value in session state"""
        st.session_state[f"config_{key}"] = value
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Retrieve configuration value from session state"""
        return st.session_state.get(f"config_{key}", default)
    
    def cache_calculation(self, key: str, result: Any):
        """Cache expensive calculation results"""
        st.session_state.cached_calculations[key] = result
    
    def get_cached_calculation(self, key: str) -> Any:
        """Retrieve cached calculation result"""
        return st.session_state.cached_calculations.get(key)
    
    def clear_uploaded_files(self):
        """Clear all uploaded files from session state"""
        st.session_state.uploaded_files = {}
        logger.info("Cleared all uploaded files from session state")
    
    def clear_processed_data(self):
        """Clear all processed data from session state"""
        st.session_state.processed_data = {}
        logger.info("Cleared all processed data from session state")
    
    def clear_cache(self):
        """Clear all cached calculations"""
        st.session_state.cached_calculations = {}
        logger.info("Cleared all cached calculations")
    
    def get_session_info(self) -> Dict:
        """Get information about current session state"""
        return {
            'uploaded_files_count': len(st.session_state.uploaded_files),
            'processed_data_count': len(st.session_state.processed_data),
            'cached_calculations_count': len(st.session_state.cached_calculations),
            'has_master_data': st.session_state.master_df is not None,
            'current_tool': st.session_state.current_tool
        }

# Global session state manager instance
session_manager = SessionStateManager()

# Convenience functions for common operations
def store_file(key: str, file_data: bytes, filename: str, file_type: str):
    """Convenience function to store uploaded file"""
    return session_manager.store_uploaded_file(key, file_data, filename, file_type)

def get_file(key: str):
    """Convenience function to retrieve uploaded file"""
    return session_manager.get_uploaded_file(key)

def store_data(key: str, data: Any):
    """Convenience function to store processed data"""
    return session_manager.store_processed_data(key, data)

def get_data(key: str):
    """Convenience function to retrieve processed data"""
    return session_manager.get_processed_data(key)

def store_master(df: pd.DataFrame, timestamp: str = None):
    """Convenience function to store master data"""
    return session_manager.store_master_data(df, timestamp)

def get_master():
    """Convenience function to retrieve master data"""
    return session_manager.get_master_data()
