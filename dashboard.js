const uploadForm = document.getElementById('uploadForm');
const salesFileInput = document.getElementById('salesFile');
const statusMessage = document.getElementById('statusMessage');

const regionFilter = document.getElementById('regionFilter');
const categoryFilter = document.getElementById('categoryFilter');
const productFilter = document.getElementById('productFilter');
const startDateFilter = document.getElementById('startDateFilter');
const endDateFilter = document.getElementById('endDateFilter');
const applyFiltersBtn = document.getElementById('applyFiltersBtn');
const resetFiltersBtn = document.getElementById('resetFiltersBtn');

let dailySalesChart;
let weeklySalesChart;
let monthlySalesChart;
let forecastSalesChart;
let categorySalesChart;
let regionSalesChart;
let topProductsChart;

let currentCategoryProductMap = {};
let allProducts = [];

function formatCurrency(value) {
    return new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(value || 0);
}

function formatNumber(value) {
    return new Intl.NumberFormat('en-IN').format(value || 0);
}

function fillSelect(selectElement, values) {
    selectElement.innerHTML = '<option value="">All</option>';
    const uniqueValues = [...new Set(values || [])].filter(v => v !== 'All' && v !== null && v !== undefined && String(v).trim() !== '');
    uniqueValues.forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        selectElement.appendChild(option);
    });
}

function populateFilters(filters) {
    fillSelect(regionFilter, filters.regions || []);
    fillSelect(categoryFilter, filters.categories || []);
    fillSelect(productFilter, filters.products || []);

    if (filters.category_product_map) {
        currentCategoryProductMap = filters.category_product_map;
    }
    // Only update allProducts if we have a full list (e.g. initial upload or not filtered by category)
    // To be safe, let's always store it if we receive it.
    if (filters.products && filters.products.length > 0) {
        // If allProducts is empty or we are resetting, we update it.
        // Actually, if we just want to keep the original list, we only update if it's currently empty,
        // or we just let it update whenever a new file is uploaded.
        // But /analyze sets allProducts, /filter-analysis might send a reduced list.
        // So we only update allProducts if we just uploaded (where we get all).
        // Let's just update it every time for now, as that's simpler.
        // Wait, if it's filtered, allProducts becomes restricted.
        // Let's check if the current category is "All". If so, save allProducts.
        if (!categoryFilter.value) {
            allProducts = filters.products;
        }
    }

    startDateFilter.min = filters.date_min || '';
    startDateFilter.max = filters.date_max || '';
    endDateFilter.min = filters.date_min || '';
    endDateFilter.max = filters.date_max || '';

    if (!startDateFilter.value) startDateFilter.value = filters.date_min || '';
    if (!endDateFilter.value) endDateFilter.value = filters.date_max || '';
}

function updateSummary(summary) {
    document.getElementById('totalRevenue').textContent = formatCurrency(summary.total_revenue);
    document.getElementById('totalRecords').textContent = formatNumber(summary.total_records);
    document.getElementById('averageSale').textContent = formatCurrency(summary.average_sale);
    document.getElementById('orderCount').textContent = formatNumber(summary.order_count);
    document.getElementById('totalQuantity').textContent = formatNumber(summary.total_quantity);
    document.getElementById('topCategory').textContent = summary.top_category || 'N/A';
    document.getElementById('topProduct').textContent = summary.top_product || 'N/A';
    document.getElementById('topRegion').textContent = summary.top_region || 'N/A';
}

function destroyIfExists(chartInstance) {
    if (chartInstance) {
        chartInstance.destroy();
    }
}

function createChart(canvasId, type, dataset, label) {
    const ctx = document.getElementById(canvasId);
    
    const colors = [
        '#4f46e5', '#818cf8', '#c7d2fe', '#312e81', '#6366f1', '#e0e7ff', '#a5b4fc', '#4338ca'
    ];
    
    let bgColor, borderColor;
    
    if (type === 'line') {
        borderColor = '#4f46e5';
        bgColor = 'rgba(79, 70, 229, 0.15)';
    } else if (type === 'bar') {
        bgColor = '#4f46e5';
        borderColor = 'transparent';
    } else {
        bgColor = colors;
        borderColor = '#ffffff';
    }

    return new Chart(ctx, {
        type,
        data: {
            labels: dataset.labels,
            datasets: [{
                label,
                data: dataset.values,
                backgroundColor: bgColor,
                borderColor: borderColor,
                borderWidth: type === 'line' ? 3 : 2,
                tension: 0.4,
                fill: type === 'line',
                borderRadius: type === 'bar' ? 6 : 0
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: { 
                legend: { 
                    display: type === 'doughnut',
                    position: 'bottom',
                    labels: { font: { family: "'Inter', sans-serif" } }
                },
                tooltip: {
                    backgroundColor: 'rgba(15, 23, 42, 0.9)',
                    titleFont: { family: "'Outfit', sans-serif", size: 14 },
                    bodyFont: { family: "'Inter', sans-serif", size: 13 },
                    padding: 12,
                    cornerRadius: 8,
                    displayColors: false
                }
            },
            scales: type === 'doughnut' ? {} : { 
                y: { 
                    beginAtZero: true,
                    grid: { color: 'rgba(0,0,0,0.04)', drawBorder: false },
                    ticks: { font: { family: "'Inter', sans-serif", size: 11 } }
                },
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { font: { family: "'Inter', sans-serif", size: 11 } }
                }
            },
            interaction: {
                intersect: false,
                mode: 'index',
            },
        }
    });
}

function updateCharts(charts) {
    destroyIfExists(dailySalesChart);
    destroyIfExists(weeklySalesChart);
    destroyIfExists(monthlySalesChart);
    destroyIfExists(forecastSalesChart);
    destroyIfExists(categorySalesChart);
    destroyIfExists(regionSalesChart);
    destroyIfExists(topProductsChart);

    dailySalesChart = createChart('dailySalesChart', 'line', charts.daily_sales, 'Daily Sales');
    weeklySalesChart = createChart('weeklySalesChart', 'bar', charts.weekly_sales, 'Weekly Sales');
    monthlySalesChart = createChart('monthlySalesChart', 'line', charts.monthly_sales, 'Monthly Sales');
    forecastSalesChart = createChart('forecastSalesChart', 'bar', charts.forecast_sales, 'Forecast Sales');
    categorySalesChart = createChart('categorySalesChart', 'bar', charts.category_sales, 'Category Sales');
    regionSalesChart = createChart('regionSalesChart', 'doughnut', charts.region_sales, 'Region Sales');
    topProductsChart = createChart('topProductsChart', 'bar', charts.top_products, 'Top Products');
}

function updateInsights(listId, items, emptyMessage) {
    const list = document.getElementById(listId);
    list.innerHTML = '';

    if (!items || !items.length) {
        list.innerHTML = `<li>${emptyMessage}</li>`;
        return;
    }

    items.forEach(item => {
        const li = document.createElement('li');
        li.textContent = item;
        list.appendChild(li);
    });
}

function updateDetectedColumns(columns) {
    const wrap = document.getElementById('detectedColumns');
    wrap.innerHTML = '';

    Object.entries(columns).forEach(([key, value]) => {
        const badge = document.createElement('div');
        badge.className = 'badge';
        badge.textContent = `${key}: ${value || 'Not found'}`;
        wrap.appendChild(badge);
    });
}

function updateQuality(quality) {
    const qualityWrap = document.getElementById('qualityChecks');
    qualityWrap.innerHTML = '';

    const items = [
        ['Original rows', quality.original_rows],
        ['Clean rows', quality.clean_rows],
        ['Removed rows', quality.removed_rows],
        ['Null cells', quality.null_cells],
        ['Duplicate rows', quality.duplicate_rows],
        ['Invalid sales rows', quality.invalid_sales_rows],
        ['Invalid date rows', quality.invalid_date_rows],
        ['Valid date rows', quality.valid_date_rows],
    ];

    items.forEach(([label, value]) => {
        const card = document.createElement('div');
        card.className = 'quality-card';
        card.innerHTML = `<span>${label}</span><strong>${formatNumber(value)}</strong>`;
        qualityWrap.appendChild(card);
    });

    document.getElementById('qualityScoreValue').textContent = `${quality.quality_score || 0}%`;
    document.getElementById('qualityScoreText').textContent = `Rows cleaned: ${formatNumber(quality.removed_rows)} removed during ETL quality checks.`;
}

function updateComparison(targetPrefix, comparison) {
    const valueEl = document.getElementById(`${targetPrefix}CompareValue`);
    const textEl = document.getElementById(`${targetPrefix}CompareText`);

    if (comparison.direction === 'not_available') {
        valueEl.textContent = '—';
        textEl.textContent = 'Not enough date-based data for comparison.';
        return;
    }

    const sign = comparison.change > 0 ? '+' : comparison.change < 0 ? '-' : '';
    const pct = comparison.change_pct == null ? '' : `${sign}${Math.abs(comparison.change_pct)}%`;
    valueEl.textContent = pct || `${sign}${formatCurrency(Math.abs(comparison.change))}`;
    textEl.textContent = `Current: ${formatCurrency(comparison.current)} | Previous: ${formatCurrency(comparison.previous)} | Change: ${sign}${formatCurrency(Math.abs(comparison.change))}`;
}

function updateTable(table) {
    const thead = document.querySelector('#dataTable thead');
    const tbody = document.querySelector('#dataTable tbody');
    thead.innerHTML = '';
    tbody.innerHTML = '';

    const headRow = document.createElement('tr');
    table.columns.forEach(col => {
        const th = document.createElement('th');
        th.textContent = col;
        headRow.appendChild(th);
    });
    thead.appendChild(headRow);

    table.rows.forEach(row => {
        const tr = document.createElement('tr');
        table.columns.forEach(col => {
            const td = document.createElement('td');
            td.textContent = row[col] ?? '';
            tr.appendChild(td);
        });
        tbody.appendChild(tr);
    });
}

function updateSqlInspector(queries) {
    const inspector = document.getElementById('sqlInspector');
    inspector.innerHTML = '';

    if (!queries || Object.keys(queries).length === 0) {
        inspector.innerHTML = '<p class="status-message">Upload data to see SQL equivalents.</p>';
        return;
    }

    // Define the specific cards requested by the user and their display order
    const requestedCards = [
        { key: 'category_distribution', title: 'Category Sales Distribution' },
        { key: 'daily_sales', title: 'Daily Sales Trend' },
        { key: 'monthly_sales', title: 'Monthly Sales Growth' },
        { key: 'regional_sales', title: 'Regional Sales' },
        { key: 'top_category', title: 'Top Category by Revenue' }
    ];

    requestedCards.forEach(card => {
        const data = queries[card.key];
        if (!data) return;

        const item = document.createElement('div');
        item.className = 'sql-item';
        
        const header = document.createElement('div');
        header.className = 'sql-header';
        header.innerHTML = `<strong>${card.title}</strong><span class="sql-badge">${card.key.replace('_', ' ')}</span>`;
        
        const codeBlock = document.createElement('pre');
        codeBlock.className = 'sql-code';
        codeBlock.textContent = data.sql;

        item.appendChild(header);
        item.appendChild(codeBlock);
        inspector.appendChild(item);
    });
}

function renderResult(data, updateFilters = true) {
    updateSummary(data.summary);
    updateCharts(data.charts);
    updateInsights('insightsList', data.insights, 'No insights generated.');
    updateInsights('recommendationsList', data.recommendations, 'No recommendations generated.');
    updateDetectedColumns(data.detected_columns);
    updateQuality(data.quality);
    updateComparison('monthly', data.comparisons.monthly);
    updateComparison('weekly', data.comparisons.weekly);
    updateTable(data.table);
    updateSqlInspector(data.sql_queries);
    if (updateFilters) {
        populateFilters(data.filters);
    }
}

async function sendAnalysisRequest(url, payload, isFormData = false) {
    const options = {
        method: 'POST',
        headers: {},
        body: payload
    };

    if (!isFormData) {
        options.headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(payload);
    }

    const response = await fetch(url, options);
    const data = await response.json();
    if (!response.ok) {
        throw new Error(data.error || 'Request failed.');
    }
    return data;
}

uploadForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    if (!salesFileInput.files.length) {
        statusMessage.textContent = 'Please select a file first.';
        return;
    }

    const formData = new FormData();
    formData.append('file', salesFileInput.files[0]);
    statusMessage.textContent = 'Analyzing file...';

    try {
        const data = await sendAnalysisRequest('/analyze', formData, true);
        renderResult(data, true);
        statusMessage.textContent = 'Analysis completed successfully.';
    } catch (error) {
        statusMessage.textContent = error.message;
    }
});

applyFiltersBtn.addEventListener('click', async () => {
    statusMessage.textContent = 'Applying filters...';
    try {
        const payload = {
            region: regionFilter.value,
            category: categoryFilter.value,
            product: productFilter.value,
            start_date: startDateFilter.value,
            end_date: endDateFilter.value,
        };
        const data = await sendAnalysisRequest('/filter-analysis', payload);
        renderResult(data, false); // Do not overwrite global filter options
        statusMessage.textContent = 'Filtered analysis updated successfully.';
    } catch (error) {
        statusMessage.textContent = error.message;
    }
});

categoryFilter.addEventListener('change', () => {
    const selectedCategory = categoryFilter.value;
    if (selectedCategory && currentCategoryProductMap[selectedCategory]) {
        fillSelect(productFilter, currentCategoryProductMap[selectedCategory]);
    } else {
        fillSelect(productFilter, allProducts);
    }
    // Reset product selection when category changes
    productFilter.value = '';
});

resetFiltersBtn.addEventListener('click', () => {
    regionFilter.value = '';
    categoryFilter.value = '';
    fillSelect(productFilter, allProducts);
    productFilter.value = '';
    startDateFilter.value = '';
    endDateFilter.value = '';
    statusMessage.textContent = 'Filters reset. Click Apply Filters to refresh the dashboard.';
});

// ===== Chatbot Logic =====
const chatbotWidget = document.getElementById('chatbotWidget');
const openChatBtn = document.getElementById('openChatBtn');
const closeChatBtn = document.getElementById('closeChatBtn');
const chatForm = document.getElementById('chatForm');
const chatInput = document.getElementById('chatInput');
const chatMessages = document.getElementById('chatMessages');

openChatBtn.addEventListener('click', () => {
    chatbotWidget.classList.add('active');
    openChatBtn.style.display = 'none';
});

closeChatBtn.addEventListener('click', () => {
    chatbotWidget.classList.remove('active');
    openChatBtn.style.display = 'flex';
});

function addMessage(text, sender) {
    const msg = document.createElement('div');
    msg.className = `message ${sender}`;
    msg.textContent = text;
    chatMessages.appendChild(msg);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = chatInput.value.trim();
    if (!text) return;

    addMessage(text, 'user');
    chatInput.value = '';

    // Add typing indicator
    const typingIndicator = document.createElement('div');
    typingIndicator.className = 'message bot typing';
    typingIndicator.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
    chatMessages.appendChild(typingIndicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message: text })
        });
        const data = await response.json();
        
        // Remove typing indicator
        chatMessages.removeChild(typingIndicator);

        if (data.response) {
            addMessage(data.response, 'bot');
        } else {
            addMessage('Sorry, I encountered an error: ' + (data.error || 'Unknown error'), 'bot');
        }
    } catch (error) {
        addMessage('Error: Could not connect to the server.', 'bot');
    }
});
