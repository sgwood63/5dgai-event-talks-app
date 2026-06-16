/**
 * BigQuery Release Pulse - Frontend Controller
 * Implements high-end interactive states, character count rendering,
 * timeline layouts, and Twitter intent generation.
 */

document.addEventListener('DOMContentLoaded', () => {
    // State management
    let allUpdates = [];
    let selectedUpdates = new Set();
    let currentFilter = 'all';
    let searchQuery = '';

    // Dom elements
    const refreshBtn = document.getElementById('refreshBtn');
    const retryBtn = document.getElementById('retryBtn');
    const clearFiltersBtn = document.getElementById('clearFiltersBtn');
    const searchInput = document.getElementById('searchInput');
    const categoryFilters = document.getElementById('categoryFilters');
    const feedTimeline = document.getElementById('feedTimeline');
    const loadingState = document.getElementById('loadingState');
    const errorState = document.getElementById('errorState');
    const errorMessage = document.getElementById('errorMessage');
    const emptyState = document.getElementById('emptyState');
    const statusText = document.getElementById('statusText');
    const statusIndicator = document.querySelector('.status-indicator');

    // Floating Action Bar elements
    const floatingActionBar = document.getElementById('floatingActionBar');
    const selectionCount = document.getElementById('selectionCount');
    const multiTweetBtn = document.getElementById('multiTweetBtn');
    const multiCopyBtn = document.getElementById('multiCopyBtn');
    const clearSelectionBtn = document.getElementById('clearSelectionBtn');

    // Modal elements
    const tweetComposer = document.getElementById('tweetComposer');
    const closeComposerBtn = document.getElementById('closeComposerBtn');
    const cancelTweetBtn = document.getElementById('cancelTweetBtn');
    const postTweetBtn = document.getElementById('postTweetBtn');
    const tweetTextarea = document.getElementById('tweetTextarea');
    const charCount = document.getElementById('charCount');
    const charProgressCircle = document.getElementById('charProgressCircle');
    const tweetPreviewText = document.getElementById('tweetPreviewText');

    // Progress ring constant metrics
    const circleRadius = 10;
    const circumference = 2 * Math.PI * circleRadius;
    charProgressCircle.style.strokeDasharray = `${circumference} ${circumference}`;
    charProgressCircle.style.strokeDashoffset = circumference;

    /* ==========================================================================
       Initialization & Data Fetching
       ========================================================================== */
    async function fetchReleases(forceRefresh = false) {
        setLoadingState(true);
        if (forceRefresh) {
            statusText.textContent = "Refetching feed...";
            statusIndicator.classList.add('loading');
            refreshBtn.querySelector('.icon-refresh').classList.add('spinning');
        }

        try {
            const response = await fetch(`/api/releases?refresh=${forceRefresh}`);
            const result = await response.json();

            if (result.status === 'success') {
                allUpdates = result.data.updates;
                renderFilters(allUpdates);
                applyFilterAndSearch();
                
                // Update Feed status indicator
                const updatedTime = new Date(result.data.feed_updated);
                statusText.textContent = `Updated: ${updatedTime.toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}`;
                statusIndicator.classList.remove('loading', 'error');
            } else {
                showError(result.message || 'Error occurred while loading releases.');
            }
        } catch (error) {
            console.error('Fetch error:', error);
            showError('Network error. Could not connect to the server.');
        } finally {
            setLoadingState(false);
            refreshBtn.querySelector('.icon-refresh').classList.remove('spinning');
            statusIndicator.classList.remove('loading');
        }
    }

    function setLoadingState(isLoading) {
        if (isLoading) {
            loadingState.classList.remove('hidden');
            feedTimeline.classList.add('hidden');
            errorState.classList.add('hidden');
            emptyState.classList.add('hidden');
            refreshBtn.disabled = true;
        } else {
            loadingState.classList.add('hidden');
            refreshBtn.disabled = false;
        }
    }

    function showError(msg) {
        errorMessage.textContent = msg;
        errorState.classList.remove('hidden');
        feedTimeline.classList.add('hidden');
        emptyState.classList.add('hidden');
        statusText.textContent = "Error updating feed";
        statusIndicator.classList.add('error');
    }

    /* ==========================================================================
       Rendering Methods
       ========================================================================== */
    function renderFilters(updates) {
        // Find unique types dynamically
        const types = [...new Set(updates.map(u => u.type))].sort();
        
        // Clear all except 'All'
        categoryFilters.innerHTML = '<button class="filter-tag active" data-category="all">All</button>';
        
        types.forEach(type => {
            const btn = document.createElement('button');
            btn.className = 'filter-tag';
            btn.dataset.category = type;
            btn.textContent = type;
            categoryFilters.appendChild(btn);
        });

        // Re-attach listeners to newly created tags
        categoryFilters.querySelectorAll('.filter-tag').forEach(tag => {
            tag.addEventListener('click', (e) => {
                categoryFilters.querySelectorAll('.filter-tag').forEach(t => t.classList.remove('active'));
                e.target.classList.add('active');
                currentFilter = e.target.dataset.category;
                applyFilterAndSearch();
            });
        });
    }

    function applyFilterAndSearch() {
        const filtered = allUpdates.filter(update => {
            const matchesCategory = currentFilter === 'all' || update.type === currentFilter;
            const matchesSearch = searchQuery === '' || 
                update.type.toLowerCase().includes(searchQuery) ||
                update.date.toLowerCase().includes(searchQuery) ||
                update.plain_text.toLowerCase().includes(searchQuery);
            return matchesCategory && matchesSearch;
        });

        if (filtered.length === 0) {
            feedTimeline.classList.add('hidden');
            emptyState.classList.remove('hidden');
        } else {
            emptyState.classList.add('hidden');
            feedTimeline.classList.remove('hidden');
            renderTimeline(filtered);
        }
    }

    function renderTimeline(updates) {
        feedTimeline.innerHTML = '';
        
        // Group updates by date to show timeline groups elegantly
        const grouped = {};
        updates.forEach(u => {
            if (!grouped[u.date]) grouped[u.date] = [];
            grouped[u.date].push(u);
        });

        Object.keys(grouped).forEach(date => {
            const dayContainer = document.createElement('div');
            dayContainer.className = 'timeline-day-group';

            grouped[date].forEach(update => {
                const item = document.createElement('div');
                item.className = 'timeline-item';
                
                const isSelected = selectedUpdates.has(update.id);
                const badgeClass = getBadgeClass(update.type);
                
                item.innerHTML = `
                    <div class="timeline-node"></div>
                    <article class="release-card glass ${isSelected ? 'selected' : ''}" data-id="${update.id}">
                        <div class="card-select-checkbox" role="checkbox" aria-checked="${isSelected}" aria-label="Select update"></div>
                        <header class="card-header">
                            <span class="card-date">${update.date}</span>
                            <span class="badge ${badgeClass}">${update.type}</span>
                        </header>
                        <div class="card-content">
                            ${update.html}
                        </div>
                        <footer class="card-actions">
                            <button class="btn-card-action tweet-btn" data-action="tweet" aria-label="Compose tweet about this update">
                                <svg class="icon icon-twitter" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                                </svg>
                                <span>Tweet</span>
                            </button>
                            <button class="btn-card-action copy-btn" data-action="copy" aria-label="Copy update details to clipboard">
                                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                                </svg>
                                <span>Copy details</span>
                            </button>
                            <a href="${update.url}" target="_blank" class="btn-card-action link-btn" aria-label="Open source documentation for this update">
                                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                                    <polyline points="15 3 21 3 21 9"/>
                                    <line x1="10" y1="14" x2="21" y2="3"/>
                                </svg>
                                <span>View source</span>
                            </a>
                        </footer >
                    </article>
                `;

                // Add Card-level Selection handler
                const card = item.querySelector('.release-card');
                const checkbox = item.querySelector('.card-select-checkbox');
                
                const toggleSelection = (e) => {
                    // Prevent trigger if clicking action buttons or links
                    if (e.target.closest('.card-actions') || e.target.closest('.card-content a')) return;
                    
                    e.preventDefault();
                    if (selectedUpdates.has(update.id)) {
                        selectedUpdates.delete(update.id);
                        card.classList.remove('selected');
                        checkbox.setAttribute('aria-checked', 'false');
                    } else {
                        selectedUpdates.add(update.id);
                        card.classList.add('selected');
                        checkbox.setAttribute('aria-checked', 'true');
                    }
                    updateFloatingActionBar();
                };

                card.addEventListener('click', toggleSelection);
                
                // Bind Tweet button
                item.querySelector('[data-action="tweet"]').addEventListener('click', (e) => {
                    e.stopPropagation();
                    openComposer(generateSingleTweet(update));
                });

                // Bind Copy button
                item.querySelector('[data-action="copy"]').addEventListener('click', (e) => {
                    e.stopPropagation();
                    const copyBtn = e.currentTarget;
                    const originalText = copyBtn.innerHTML;
                    
                    const details = `Google Cloud BigQuery Update (${update.date}) - ${update.type}:\n\n${update.plain_text}\n\nRead more: ${update.url}`;
                    
                    navigator.clipboard.writeText(details).then(() => {
                        copyBtn.innerHTML = `
                            <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2">
                                <polyline points="20 6 9 17 4 12"/>
                            </svg>
                            <span style="color:#34d399">Copied!</span>
                        `;
                        setTimeout(() => {
                            copyBtn.innerHTML = originalText;
                        }, 2000);
                    });
                });

                dayContainer.appendChild(item);
            });
            
            feedTimeline.appendChild(dayContainer);
        });
    }

    function getBadgeClass(type) {
        const mapping = {
            'Feature': 'badge-feature',
            'Issue': 'badge-issue',
            'Change': 'badge-change',
            'Deprecation': 'badge-deprecation',
            'Announcement': 'badge-announcement'
        };
        return mapping[type] || 'badge-update';
    }

    /* ==========================================================================
       Tweet Text Generation Rules
       ========================================================================== */
    function generateSingleTweet(update) {
        const header = `🚀 #BigQuery ${update.type} (${update.date}):\n\n`;
        const footer = `\n\nRead more: ${update.url}`;
        
        // 280 character limit limit logic
        const maxBodyLen = 280 - header.length - footer.length - 5;
        let body = update.plain_text;
        
        if (body.length > maxBodyLen) {
            body = body.substring(0, maxBodyLen - 3) + "...";
        }
        
        return `${header}${body}${footer}`;
    }

    function generateMultiTweet() {
        const selectedList = allUpdates.filter(u => selectedUpdates.has(u.id));
        if (selectedList.length === 0) return '';
        
        if (selectedList.length === 1) {
            return generateSingleTweet(selectedList[0]);
        }

        // Combined tweet format
        const header = `🚀 Google Cloud #BigQuery Updates (${selectedList.length}):\n\n`;
        const footer = `\n\nNotes feed: https://cloud.google.com/bigquery/docs/release-notes`;
        
        let body = '';
        selectedList.forEach((u, i) => {
            body += `• [${u.type}] ${u.plain_text}\n`;
        });

        const maxBodyLen = 280 - header.length - footer.length - 5;
        if (body.length > maxBodyLen) {
            body = body.substring(0, maxBodyLen - 3) + "...";
        }

        return `${header}${body}${footer}`;
    }

    function getCombinedPlainDetails() {
        const selectedList = allUpdates.filter(u => selectedUpdates.has(u.id));
        let details = `Google Cloud BigQuery Updates - ${selectedList.length} Items:\n\n`;
        selectedList.forEach(u => {
            details += `[${u.date}] ${u.type}:\n${u.plain_text}\nSource: ${u.url}\n\n-----------------\n\n`;
        });
        return details.trim();
    }

    /* ==========================================================================
       Selection Bar State Handlers
       ========================================================================== */
    function updateFloatingActionBar() {
        const count = selectedUpdates.size;
        selectionCount.textContent = `${count} update${count !== 1 ? 's' : ''} selected`;
        
        if (count > 0) {
            floatingActionBar.classList.remove('hidden');
            // Allow animation to trigger
            setTimeout(() => floatingActionBar.classList.add('visible'), 50);
        } else {
            floatingActionBar.classList.remove('visible');
            // Hide from DOM after transition finishes
            setTimeout(() => {
                if (selectedUpdates.size === 0) {
                    floatingActionBar.classList.add('hidden');
                }
            }, 300);
        }
    }

    function clearAllSelection() {
        selectedUpdates.clear();
        document.querySelectorAll('.release-card').forEach(card => {
            card.classList.remove('selected');
            const checkbox = card.querySelector('.card-select-checkbox');
            if (checkbox) checkbox.setAttribute('aria-checked', 'false');
        });
        updateFloatingActionBar();
    }

    /* ==========================================================================
       Tweet Composer Dialog logic
       ========================================================================== */
    function openComposer(initialText) {
        tweetTextarea.value = initialText;
        updateCharProgress();
        tweetComposer.showModal();
        tweetTextarea.focus();
    }

    function closeComposer() {
        tweetComposer.close();
    }

    function updateCharProgress() {
        const text = tweetTextarea.value;
        const length = text.length;
        const remaining = 280 - length;
        
        charCount.textContent = remaining;
        
        // Progress percentage calculation
        const percent = Math.min(length / 280, 1);
        const offset = circumference - (percent * circumference);
        charProgressCircle.style.strokeDashoffset = offset;

        // Color coding progress circle
        if (remaining < 0) {
            charProgressCircle.style.stroke = '#ef4444'; // Red
            charCount.style.color = '#ef4444';
            postTweetBtn.disabled = true;
        } else if (remaining <= 20) {
            charProgressCircle.style.stroke = '#fbbf24'; // Orange
            charCount.style.color = '#fbbf24';
            postTweetBtn.disabled = false;
        } else {
            charProgressCircle.style.stroke = '#3b82f6'; // Blue
            charCount.style.color = 'hsl(var(--text-secondary))';
            postTweetBtn.disabled = false;
        }

        // Update tweet preview area
        renderTweetPreview(text);
    }

    function renderTweetPreview(text) {
        // Highlighting hashtags and links in preview
        let html = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
            
        // Regex highlight hashtags (#tag)
        html = html.replace(/(#[a-zA-Z0-9_]+)/g, '<span class="highlight-hashtag">$1</span>');
        
        // Regex highlight links (http/https)
        html = html.replace(/(https?:\/\/[^\s]+)/g, '<span class="highlight-link">$1</span>');

        tweetPreviewText.innerHTML = html;
    }

    /* ==========================================================================
       Fallback for light-dismiss dialog (backdrop click to close)
       ========================================================================== */
    if (!('closedBy' in HTMLDialogElement.prototype)) {
        tweetComposer.addEventListener('click', (event) => {
            if (event.target !== tweetComposer) return;
            
            const rect = tweetComposer.getBoundingClientRect();
            const isClickInside = (
                rect.top <= event.clientY &&
                event.clientY <= rect.top + rect.height &&
                rect.left <= event.clientX &&
                event.clientX <= rect.left + rect.width
            );
            
            if (!isClickInside) {
                tweetComposer.close();
            }
        });
    }

    /* ==========================================================================
       Event Listeners Binding
       ========================================================================== */
    refreshBtn.addEventListener('click', () => fetchReleases(true));
    retryBtn.addEventListener('click', () => fetchReleases(true));
    
    clearFiltersBtn.addEventListener('click', () => {
        searchInput.value = '';
        searchQuery = '';
        currentFilter = 'all';
        categoryFilters.querySelectorAll('.filter-tag').forEach(t => {
            t.classList.toggle('active', t.dataset.category === 'all');
        });
        applyFilterAndSearch();
    });

    searchInput.addEventListener('input', (e) => {
        searchQuery = e.target.value.toLowerCase().trim();
        applyFilterAndSearch();
    });

    // Selection Bar Buttons
    clearSelectionBtn.addEventListener('click', clearAllSelection);
    
    multiCopyBtn.addEventListener('click', (e) => {
        const textToCopy = getCombinedPlainDetails();
        const originalText = multiCopyBtn.innerHTML;
        
        navigator.clipboard.writeText(textToCopy).then(() => {
            multiCopyBtn.innerHTML = `
                <svg class="icon" viewBox="0 0 24 24" fill="none" stroke="#34d399" stroke-width="2">
                    <polyline points="20 6 9 17 4 12"/>
                </svg>
                <span style="color:#34d399">Copied updates!</span>
            `;
            setTimeout(() => {
                multiCopyBtn.innerHTML = originalText;
            }, 2000);
        });
    });

    multiTweetBtn.addEventListener('click', () => {
        openComposer(generateMultiTweet());
    });

    // Composer Actions
    tweetTextarea.addEventListener('input', updateCharProgress);
    
    closeComposerBtn.addEventListener('click', closeComposer);
    cancelTweetBtn.addEventListener('click', closeComposer);
    
    postTweetBtn.addEventListener('click', () => {
        const text = tweetTextarea.value;
        const twitterIntentUrl = `https://twitter.com/intent/tweet?text=${encodeURIComponent(text)}`;
        
        // Open Twitter Web Intent
        window.open(twitterIntentUrl, '_blank', 'noopener,noreferrer');
        
        // Close modal and clear selection for cleanliness
        closeComposer();
        clearAllSelection();
    });

    // Initial Fetch
    fetchReleases(false);
});
