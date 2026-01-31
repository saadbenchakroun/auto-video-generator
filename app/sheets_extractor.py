import gspread
from google.oauth2.service_account import Credentials
from typing import Optional, Tuple, Dict, Any, List
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SheetConnectionError(Exception):
    """Raised when connection to Google Sheets fails."""
    pass


class SheetError(Exception):
    """Raised when sheet operations fail."""
    pass


class SheetsExtractor:
    def __init__(self, credentials_file: str, sheets_id: str, worksheet_name: str):
        """
        Initialize the SheetsExtractor.
        
        Args:
            credentials_file: Path to the service account credentials JSON file
            sheets_id: Google Sheets spreadsheet ID
            worksheet_name: Name of the worksheet to work with
        """
        self.credentials_file = credentials_file
        self.sheets_id = sheets_id
        self.worksheet_name = worksheet_name
        self.client = None
        self.worksheet = None
        self._headers = {}

    def _connect(self):
        """
        Authenticates and connects to the worksheet.
        
        Raises:
            SheetConnectionError: If connection fails
        """
        try:
            logger.info("Attempting to authenticate and connect to Google Sheets...")
            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive"
            ]
            # Create credentials from service account JSON. The selected scopes allow
            # access to spreadsheets and drive (for opening by key).
            creds = Credentials.from_service_account_file(self.credentials_file, scopes=scopes)
            self.client = gspread.authorize(creds)

            # Open spreadsheet by its ID, then access the named worksheet.
            spreadsheet = self.client.open_by_key(self.sheets_id)
            self.worksheet = spreadsheet.worksheet(self.worksheet_name)
            
            # Cache headers: read first row and build a mapping from normalized header
            # name -> 1-based column index. Normalization ensures lookups are case-insensitive
            # and tolerant of surrounding whitespace.
            header_row = self.worksheet.row_values(1)
            self._headers = {
                header.strip().lower(): i + 1 
                for i, header in enumerate(header_row) 
                if header.strip()
            }
            
            # If headers are empty, further operations that rely on column names will fail,
            # so raise early with a clear error.
            if not self._headers:
                raise SheetConnectionError("No headers found in worksheet")
            
            logger.info(f"Successfully connected to worksheet: {self.worksheet.title}")
            logger.info(f"Found {len(self._headers)} columns: {list(self._headers.keys())}")
            
        except gspread.exceptions.SpreadsheetNotFound:
            error_msg = f"Spreadsheet with ID '{self.sheets_id}' not found"
            logger.error(error_msg)
            raise SheetConnectionError(error_msg)
        except gspread.exceptions.WorksheetNotFound:
            error_msg = f"Worksheet '{self.worksheet_name}' not found"
            logger.error(error_msg)
            raise SheetConnectionError(error_msg)
        except Exception as e:
            # Catch-all to wrap any unexpected exceptions in a SheetConnectionError;
            # this keeps error types consistent for callers.
            error_msg = f"Unexpected error during connection: {e}"
            logger.error(error_msg)
            raise SheetConnectionError(error_msg)

    def _get_column_index(self, column_name: str) -> int:
        """
        Gets the 1-based index of a column from its name.
        
        Args:
            column_name: Name of the column
            
        Returns:
            1-based column index
            
        Raises:
            SheetError: If column not found
        """
        # Normalize the lookup key to match how headers were cached.
        col_index = self._headers.get(column_name.strip().lower())
        if col_index is None:
            # Provide helpful context in the error listing available column names.
            available_columns = ', '.join(self._headers.keys())
            error_msg = f"Column '{column_name}' not found. Available columns: {available_columns}"
            logger.error(error_msg)
            raise SheetError(error_msg)
        return col_index

    def _ensure_connected(self, reconnect: bool = False):
        """
        Ensures connection to worksheet exists, reconnecting if needed.
        
        Args:
            reconnect: Force reconnection even if already connected
        """
        # Only reconnect when explicitly requested or if worksheet reference is missing.
        if reconnect or not self.worksheet:
            self._connect()

    def find_row_and_get_data(
        self, 
        column_name: str, 
        keyword: str = "", 
        reconnect: bool = False
    ) -> Optional[Tuple[int, Dict[str, str]]]:
        """
        Finds the first row matching a keyword in the specified column.
        
        Args:
            column_name: Name of the column to search in
            keyword: Keyword to search for (empty string finds first empty cell)
            reconnect: Force reconnection to Google Sheets
            
        Returns:
            Tuple of (row_number, row_data_dict) or None if not found
            
        Raises:
            SheetError: If search operation fails
        """
        self._ensure_connected(reconnect)
        col_index = self._get_column_index(column_name)

        try:
            # Read all values in the column. Note: gspread returns a list with header included.
            col_values = self.worksheet.col_values(col_index)
            row_number = None

            # Search for matching row (skip header row).
            # enumerate starts at 2 to reflect actual sheet row numbers (1 is header).
            for i, cell_value in enumerate(col_values[1:], start=2):
                # If keyword is empty, search for the first empty cell (after trimming whitespace).
                if keyword == "" and not cell_value.strip():
                    row_number = i
                    break
                # Otherwise look for a case-insensitive substring match.
                elif keyword != "" and keyword.lower() in cell_value.lower():
                    row_number = i
                    break
            
            # If searching for an empty cell and none was found, return the next available row
            # (i.e., append behavior) which is length_of_column + 1 because col_values omits
            # trailing empty cells beyond the last non-empty cell.
            if keyword == "" and row_number is None:
                row_number = len(col_values) + 1
            
            if row_number is None:
                # No match found for non-empty keyword searches.
                logger.warning(
                    f"No row found matching keyword '{keyword}' in column '{column_name}'"
                )
                return None
            
            # Get row data for the found row. row_values may be shorter than number of headers,
            # so map missing cells to empty strings.
            row_data_list = self.worksheet.row_values(row_number)
            # header_list must be ordered by column index; self._headers stores mapping header->index,
            # so we sort by the index to reconstruct the original left-to-right header order.
            header_list = [h for h, i in sorted(self._headers.items(), key=lambda item: item[1])]
            
            row_data_dict = {
                header: row_data_list[i] if i < len(row_data_list) else '' 
                for i, header in enumerate(header_list)
            }
            
            logger.info(f"Found matching row at row number {row_number}")
            return row_number, row_data_dict
        
        except Exception as e:
            # Wrap lower-level exceptions with SheetError to keep surface API consistent.
            error_msg = f"Error searching sheet: {e}"
            logger.error(error_msg)
            raise SheetError(error_msg)

    def find_multiple_rows_and_get_data(
        self, 
        column_name: str, 
        keyword: str, 
        max_results: Optional[int] = None,
        reconnect: bool = False
    ) -> List[Tuple[int, Dict[str, str]]]:
        """
        Finds multiple rows matching a keyword in the specified column.
        """
        self._ensure_connected(reconnect)
        col_index = self._get_column_index(column_name)
        # Convert 1-based column index to 0-based list index
        target_idx = col_index - 1

        try:
            # Fetch ALL values to avoid truncation of empty trailing cells
            all_rows = self.worksheet.get_all_values()
            
            if not all_rows:
                return []
                
            matching_rows = []
            
            # Helper to reconstruct dict
            # header_list ordered by index to match row list order
            header_list = [h for h, idx in sorted(self._headers.items(), key=lambda item: item[1])]

            # Skip header row (index 0), start row numbering at 2
            for i, row_values in enumerate(all_rows[1:], start=2):
                # Safely get the cell value
                if target_idx < len(row_values):
                    cell_value = row_values[target_idx]
                else:
                    cell_value = "" # Treat missing cells as empty
                
                # Check for match
                match = False
                if keyword == "":
                    # Empty search: match empty string or whitespace
                    if not cell_value.strip():
                        match = True
                else:
                    # Substring match
                    if keyword.lower() in cell_value.lower():
                        match = True
                
                if match:
                    # Map row to dict
                    row_data_dict = {
                        header: row_values[j] if j < len(row_values) else '' 
                        for j, header in enumerate(header_list)
                    }
                    
                    matching_rows.append((i, row_data_dict))
                    
                    if max_results and len(matching_rows) >= max_results:
                        break
                        
            logger.info(
                f"Found {len(matching_rows)} row(s) matching keyword '{keyword}' "
                f"in column '{column_name}'"
            )
            return matching_rows
        
        except Exception as e:
            error_msg = f"Error searching sheet for multiple rows: {e}"
            logger.error(error_msg)
            raise SheetError(error_msg)

    def update_cell(
        self, 
        row_number: int, 
        column_name: str, 
        value: Any, 
        reconnect: bool = False
    ):
        """
        Updates a single cell in the worksheet.
        
        Args:
            row_number: Row number (1-based)
            column_name: Name of the column
            value: Value to set
            reconnect: Force reconnection to Google Sheets
            
        Raises:
            SheetError: If update operation fails
        """
        self._ensure_connected(reconnect)
        col_index = self._get_column_index(column_name)

        try:
            self.worksheet.update_cell(row_number, col_index, str(value))
            logger.info(f"Cell ({row_number}, '{column_name}') updated successfully to '{value}'")
        except Exception as e:
            error_msg = f"Error updating cell ({row_number}, '{column_name}'): {e}"
            logger.error(error_msg)
            raise SheetError(error_msg)

    def update_multiple_cells(
        self, 
        updates: List[Tuple[int, str, Any]], 
        reconnect: bool = False
    ):
        """
        Updates multiple cells in a single batch operation for efficiency.
        
        Args:
            updates: List of tuples (row_number, column_name, value)
            reconnect: Force reconnection to Google Sheets
            
        Raises:
            SheetError: If batch update operation fails
            
        Example:
            updates = [
                (2, 'Status', 'Complete'),
                (3, 'Status', 'Pending'),
                (2, 'Notes', 'Updated via API')
            ]
            extractor.update_multiple_cells(updates)
        """
        self._ensure_connected(reconnect)
        
        if not updates:
            logger.warning("No updates provided")
            return

        try:
            # Prepare batch update data in A1 notation. Using batch_update is more efficient
            # than calling update_cell repeatedly when many updates are required.
            batch_data = []
            for row_number, column_name, value in updates:
                col_index = self._get_column_index(column_name)
                # Convert numeric row/col to A1-style address (e.g., 'B3').
                # This is required by batch_update range format.
                cell_address = gspread.utils.rowcol_to_a1(row_number, col_index)
                batch_data.append({
                    'range': cell_address,
                    'values': [[str(value)]]
                })
            
            # Execute the batch update. The worksheet API will apply all ranges provided.
            self.worksheet.batch_update(batch_data)
            logger.info(f"Successfully updated {len(updates)} cells in batch")
            
        except Exception as e:
            error_msg = f"Error during batch update: {e}"
            logger.error(error_msg)
            raise SheetError(error_msg)

    def update_row(
        self, 
        row_number: int, 
        data: Dict[str, Any], 
        reconnect: bool = False
    ):
        """
        Updates multiple cells in a single row.
        
        Args:
            row_number: Row number (1-based)
            data: Dictionary mapping column names to values
            reconnect: Force reconnection to Google Sheets
            
        Raises:
            SheetError: If update operation fails
            
        Example:
            extractor.update_row(5, {
                'Status': 'Complete',
                'Notes': 'All done',
                'Date': '2025-11-12'
            })
        """
        # Convert the row dictionary into the (row, column_name, value) tuples required
        # by update_multiple_cells. This keeps a single implementation for batching.
        updates = [(row_number, col_name, value) for col_name, value in data.items()]
        self.update_multiple_cells(updates, reconnect)
        logger.info(f"Row {row_number} updated with {len(data)} field(s)")


# Example usage
if __name__ == "__main__":
    # Initialize extractor
    extractor = SheetsExtractor(
        credentials_file="credentials.json",
        sheets_id="1zoTVjy4fyoSkrbLYVBJpT2N-48mh1r0PTD-ylzXx2DE",
        worksheet_name="newScripts"
    )
    
    # try:
    #     # Find single row
    #     result = extractor.find_row_and_get_data("Create-Status", "")
    #     if result:
    #         row_num, data = result
    #         print(f"Found row {row_num}: {data}")
        
    #     # Find multiple rows
    #     results = extractor.find_multiple_rows_and_get_data("Reel-Status", "", max_results=5)
    #     print(f"Found {len(results)} pending items")
        
    #     # Update single cell
    #     extractor.update_cell(99, "Create-Status", "working")
        
    #     # Update multiple cells
    #     extractor.update_multiple_cells([
    #         (100, "Reel-Status", "completed"),
    #         (101, "Short-Status", "in progress"),
    #         (102, "Create-Status", "Updated today")
    #     ])
        
        
    # except (SheetConnectionError, SheetError) as e:
    #     logger.error(f"Operation failed: {e}")

    result = extractor.find_row_and_get_data("Created", "")
    if result is None:
        print("[INFO] No pending scripts found. Exiting.")
        exit(0)
    row_number, data = result
    id = data.get('id', '0000')
    script = data.get('script', 'placeholder script')
    
    print("Row number:", row_number)
    print("found id:", id)
    print("found script:", script)