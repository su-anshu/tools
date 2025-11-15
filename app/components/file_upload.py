"""
Enhanced File Upload Component with Drag & Drop
"""
import streamlit as st
from typing import List, Optional
import pandas as pd

def enhanced_file_upload(
    label: str,
    file_types: List[str],
    accept_multiple: bool = True,
    help_text: str = "",
    max_size_mb: float = 50
) -> Optional[List]:
    """
    Enhanced file upload with visual feedback
    
    Args:
        label: Upload label
        file_types: List of accepted file types
        accept_multiple: Allow multiple files
        help_text: Help text for upload
        max_size_mb: Maximum file size in MB
    
    Returns:
        List of uploaded files or None
    """
    st.markdown(f"""
    <div style="border: 2px dashed #E0E0E0;
                border-radius: 12px;
                padding: 1.5rem;
                text-align: center;
                background: #FAFAFA;
                margin: 0.75rem 0;
                transition: all 0.3s ease;">
        <div style="font-size: 2.5rem; margin-bottom: 0.4rem;">📤</div>
        <p style="color: #757575; margin: 0.4rem 0; font-size: 0.9rem;">
            Drag and drop files here or click to browse
        </p>
        <p style="color: #9E9E9E; margin: 0; font-size: 0.8rem;">
            Accepted: {', '.join(file_types).upper()} • Max {max_size_mb}MB per file
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    uploaded_files = st.file_uploader(
        label,
        type=file_types,
        accept_multiple_files=accept_multiple,
        help=help_text,
        label_visibility="collapsed"
    )
    
    if uploaded_files:
        return _display_file_list(uploaded_files, max_size_mb)
    
    return None

def _display_file_list(files: List, max_size_mb: float) -> List:
    """Display uploaded files with details - Compact version"""
    st.markdown("### 📋 Uploaded Files")
    
    total_size = sum(f.size for f in files)
    total_size_mb = total_size / (1024 * 1024)
    
    # File list - Compact
    for idx, file in enumerate(files):
        file_size_mb = file.size / (1024 * 1024)
        file_size_str = f"{file_size_mb:.2f} MB" if file_size_mb >= 1 else f"{file.size / 1024:.2f} KB"
        
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.markdown(f"""
            <div style="display: flex; align-items: center; gap: 0.4rem; padding: 0.4rem 0;">
                <span style="font-size: 1rem;">📄</span>
                <div>
                    <strong style="font-size: 0.9rem;">{file.name}</strong>
                    <div style="font-size: 0.8rem; color: #757575;">{file_size_str}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            status_color = "#4CAF50" if file_size_mb <= max_size_mb else "#FFB74D"
            status_text = "Ready" if file_size_mb <= max_size_mb else "Too Large"
            st.markdown(f"""
            <div style="color: {status_color}; font-weight: 600; padding: 0.4rem 0; font-size: 0.85rem;">
                {status_text}
            </div>
            """, unsafe_allow_html=True)
        with col3:
            if st.button("🗑️", key=f"remove_{idx}", help="Remove file"):
                # Note: Streamlit doesn't support removing files from list directly
                # This would need session state management
                st.warning("File removal requires page refresh. Please re-upload files.")
    
    # Summary - Compact metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Files", len(files))
    with col2:
        st.metric("Total Size", f"{total_size_mb:.2f} MB")
    with col3:
        avg_size = total_size_mb / len(files) if files else 0
        st.metric("Avg Size", f"{avg_size:.2f} MB")
    
    return files

