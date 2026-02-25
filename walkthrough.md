# Walkthrough - Reporte de Movimientos de Cartera

This document details the implementation of the "Wallet Movements Report" feature.

## 1. Overview
We have created a comprehensive report for analyzing wallet movements (`Movimientos_Cartera`). The report provides key financial insights, including income by branch, payments by provider, and charges by provider. It also includes a detailed transaction history enriched with invoice status and remaining balance information.

## 2. Key Features

### A. Aggregate Data & KPIs
- **Total Income**: Sum of all `INGRESO` movements.
- **Total Payments**: Sum of all `PAGO` movements.
- **Total Charges**: Sum of all `CARGO` movements.
- **Net Balance**: Total Income - Total Payments.

### B. Visualizations
1.  **Daily Evolution**: A combo chart showing daily trends for Income vs. Payments.
2.  **Income by Branch**: A doughnut chart showing the distribution of income across different branches. Movements without a branch are labeled as "Sin Sucursal".
3.  **Payments by Provider**: A horizontal bar chart showing the top 10 providers by payment volume. Payments without a provider are labeled as "Sin Proveedor".
4.  **Charges by Provider**: A horizontal bar chart showing the top 10 providers by debt/charges. Charges without a provider are labeled as "Sin Proveedor".

### C. Detailed Transaction List
- Displays a chronological list of movements.
- **Enriched Data**: For movements related to an invoice, it shows:
    - **Provider Name**
    - **Invoice Folio**
    - **Current Invoice Status** (e.g., Pending, Paid)
    - **Remaining Balance** (Calculated dynamically)

### D. Filtering
- Users can filter the report by:
    - **Date Range** (Start/End)
    - **Movement Type** (Income, Payment, Charge)
    - **Branch** (for incomes)
    - **Provider** (for payments/charges)

## 3. Technical Implementation

### Core Service (`core/services/reporte_movimientos.py`)
- **Logic**: Aggregates data using Django's ORM (`Sum`, `Count`).
- **Data Preparation**: Prepares JSON-serializable lists for Chart.js.
- **Enrichment**: Iterates through the detailed list to calculate `monto_restante_factura` using the `servicio_obtener_monto_restante_por_pagar_factura` service.

### View (`core/views.py`)
- **`reporte_movimientos`**: Handles HTTP requests, extracts filter parameters from POST/GET, calls the service, and renders the template.

### Template (`templates/core/reportes/movimientos/reporte_movimientos.html`)
- **Design**: Uses a modern glassmorphism aesthetic.
- **Interactivity**: Uses `Chart.js` for responsive and interactive charts.
- **Responsiveness**: Grid layouts adapt to different screen sizes.

## 4. How to Test
1.  Navigate to the **Reportes** menu and select **Movimientos**.
2.  Use the filter form to select a date range.
3.  Observe the KPIs and Charts updating.
4.  Scroll down to the "Últimos Movimientos" table.
5.  Verify that payments related to invoices show the "Estado" and "Restan" fields.

## 5. Files Created/Modified
- `core/services/reporte_movimientos.py` (New)
- `core/views.py` (Modified)
- `core/urls.py` (Modified)
- `templates/core/reportes/movimientos/reporte_movimientos.html` (New)
- `templates/base.html` (Modified)
