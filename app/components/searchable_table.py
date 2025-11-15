"""
Searchable Dataframe Component
"""
import streamlit as st
import pandas as pd
from typing import List, Optional

def searchable_dataframe(
    df: pd.DataFrame,
    title: str,
    search_columns: Optional[List[str]] = None,
    height: int = 400,
    show_export: bool = True,
    key_prefix: str = "table"
):
    """
    Display searchable dataframe with filters
    
    Args:
        df: DataFrame to display
        title: Table title
        search_columns: Columns to search in (None = all string columns)
        height: Table height in pixels
        show_export: Show export button
        key_prefix: Unique key prefix for widgets
    """
    if df.empty:
        st.info(f"No data available for {title}")
        return df
    
    st.markdown(f"### {title}")
    
    # Search and filter row
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        search_term = st.text_input(
            "🔍 Search",
            key=f"{key_prefix}_search",
            placeholder="Search in table...",
            help="Search across all columns"
        )
    
    with col2:
        if 'Status' in df.columns:
            status_filter = st.selectbox(
                "Filter by Status",
                ["All", "Ready", "Missing FNSKU", "Missing FROM MASTER"],
                key=f"{key_prefix}_status_filter"
            )
        else:
            status_filter = "All"
    
    with col3:
        st.markdown(f"<div style='padding-top: 1.5rem; color: #757575;'>Total: {len(df)} rows</div>", 
                   unsafe_allow_html=True)
    
    # Filter dataframe
    filtered_df = df.copy()
    
    # Apply search filter
    if search_term:
        mask = pd.Series([False] * len(filtered_df))
        search_cols = search_columns if search_columns else filtered_df.select_dtypes(include=['object']).columns
        
        for col in search_cols:
            if col in filtered_df.columns:
                mask |= filtered_df[col].astype(str).str.contains(search_term, case=False, na=False)
        
        filtered_df = filtered_df[mask]
    
    # Apply status filter
    if status_filter != "All" and 'Status' in filtered_df.columns:
        if status_filter == "Ready":
            filtered_df = filtered_df[filtered_df['Status'].str.contains('READY', case=False, na=False)]
        elif status_filter == "Missing FNSKU":
            filtered_df = filtered_df[filtered_df['Status'].str.contains('MISSING FNSKU', case=False, na=False)]
        elif status_filter == "Missing FROM MASTER":
            filtered_df = filtered_df[filtered_df['Status'].str.contains('MISSING FROM MASTER', case=False, na=False)]
    
    # Show filtered count
    if len(filtered_df) != len(df):
        st.caption(f"Showing {len(filtered_df)} of {len(df)} rows")
    
    # Display table - Compact version with reduced default height
    display_height = min(height, 300)  # Cap at 300px for compact UI
    st.dataframe(filtered_df, use_container_width=True, height=display_height)
    
    # Export button
    if show_export and not filtered_df.empty:
        from io import BytesIO
        csv_buffer = BytesIO()
        filtered_df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)
        
        st.download_button(
            "📥 Export to CSV",
            data=csv_buffer,
            file_name=f"{title.replace(' ', '_')}.csv",
            mime="text/csv",
            key=f"{key_prefix}_export"
        )
    
    return filtered_df

