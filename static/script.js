document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('config-form');
    const saveMsg = document.getElementById('save-msg');
    
    const statusBadge = document.getElementById('market-status');
    const lastPriceEl = document.getElementById('last-price');
    const lastUpdateEl = document.getElementById('last-update');
    
    const tickerInput = document.getElementById('ticker');
    const datalist = document.getElementById('stock-options');

    let searchTimeout;
    tickerInput.addEventListener('input', (e) => {
        const query = e.target.value;
        if (!query) return;
        
        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(() => {
            fetch(`/api/search?q=${encodeURIComponent(query)}`)
                .then(res => res.json())
                .then(data => {
                    datalist.innerHTML = '';
                    data.results.forEach(stock => {
                        const option = document.createElement('option');
                        option.value = stock.symbol;
                        option.textContent = stock.name;
                        datalist.appendChild(option);
                    });
                })
                .catch(err => console.error("Search error:", err));
        }, 300);
    });

    // Fetch initial config
    fetch('/api/config')
        .then(res => res.json())
        .then(data => {
            document.getElementById('ticker').value = data.ticker || '';
            document.getElementById('mode').value = data.mode || 'portfolio';
            document.getElementById('expected').value = data.expected || '';
            document.getElementById('poll_seconds').value = data.poll_seconds || '';
            document.getElementById('stop_loss').value = data.stop_loss || '';
            document.getElementById('target').value = data.target || '';
        })
        .catch(err => console.error("Error loading config:", err));

    let saveTimeout;
    form.addEventListener('input', (e) => {
        clearTimeout(saveTimeout);
        saveTimeout = setTimeout(() => {
            const payload = {
                ticker: document.getElementById('ticker').value,
                mode: document.getElementById('mode').value,
                expected: parseFloat(document.getElementById('expected').value) || 0,
                poll_seconds: parseInt(document.getElementById('poll_seconds').value) || 5,
                stop_loss: parseFloat(document.getElementById('stop_loss').value) || 0,
                target: parseFloat(document.getElementById('target').value) || 0
            };

            fetch('/api/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                saveMsg.textContent = "Live Saved ✅";
                saveMsg.classList.add('show');
                setTimeout(() => saveMsg.classList.remove('show'), 2000);
            })
            .catch(err => console.error("Error saving config:", err));
        }, 800);
    });

    // Prevent enter key from submitting and refreshing
    form.addEventListener('submit', e => e.preventDefault());

    // Poll status every 2 seconds
    setInterval(() => {
        fetch('/api/status')
            .then(res => res.json())
            .then(data => {
                if (data.market_status === 'OPEN') {
                    statusBadge.textContent = 'OPEN';
                    statusBadge.className = 'badge open';
                } else if (data.market_status === 'CLOSED') {
                    statusBadge.textContent = 'CLOSED';
                    statusBadge.className = 'badge closed';
                } else {
                    statusBadge.textContent = data.market_status;
                    statusBadge.className = 'badge';
                }
                
                if (data.last_price !== null) {
                    lastPriceEl.textContent = '₹' + parseFloat(data.last_price).toFixed(2);
                }
                if (data.last_update) {
                    lastUpdateEl.textContent = data.last_update;
                }
            })
            .catch(err => console.error("Error fetching status:", err));
    }, 2000);
});
