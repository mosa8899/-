document.addEventListener('DOMContentLoaded', () => {
    const inProgressOrdersContainer = document.getElementById('in-progress-orders');
    const completedOrdersContainer = document.getElementById('completed-orders');
    const restaurantNameH1 = document.getElementById('restaurant-name');
    const orderSearchInput = document.getElementById('order-search');
    const searchButton = document.getElementById('search-button');
    const statusContainer = document.getElementById('status-container');

    
    // Store orders to track changes
    let currentOrders = {
        inProgress: [],
        completed: []
    };
    
    // حالة البحث
    let isSearchActive = false;
    let searchedOrderNumber = null;
    
    // Fetch restaurant config
    let preparationTimeMinutes = 10; // قيمة افتراضية
    let autoRemoveCompletedOrdersMinutes = 20; // قيمة افتراضية لوقت المسح التلقائي
    
    async function fetchConfig() {
        try {
            const response = await fetch('/api/config');
            const config = await response.json();
            restaurantNameH1.textContent = config.restaurant_name || 'حالة الطلبات';
            preparationTimeMinutes = config.preparation_time_minutes || 10;
            autoRemoveCompletedOrdersMinutes = config.auto_remove_completed_orders_minutes || 20;
        } catch (error) {
            console.error('Failed to fetch restaurant config:', error);
        }
    }
    
    // Fetch orders status
    async function fetchOrdersStatus() {
        try {
            const response = await fetch('/api/orders_status');
            const data = await response.json();
            
            // Limit the number of displayed orders for better performance
            const maxDisplayedOrders = 30; // Adjust based on performance testing
            
            // Keep only the most recent orders
            const inProgressOrders = data.inProgress.slice(0, maxDisplayedOrders);
            const completedOrders = data.completed.slice(0, maxDisplayedOrders);
            
            // Update the UI with new data
            updateOrdersDisplay(inProgressOrders, completedOrders);
            
            // Update total counts (including non-displayed orders)
            document.getElementById('in-progress-count').textContent = data.inProgress.length;
            document.getElementById('completed-count').textContent = data.completed.length;
            
            // Update page title with total counts
            document.title = `(${data.inProgress.length}/${data.completed.length}) حالة الطلبات`;
            
        } catch (error) {
            console.error('Failed to fetch orders status:', error);
            // If API fails, show error message after a few attempts
            if (!document.querySelector('.error-message')) {
                const errorMsg = document.createElement('div');
                errorMsg.className = 'error-message';
                errorMsg.textContent = 'تعذر الاتصال بالخادم. جاري إعادة المحاولة...';
                document.body.appendChild(errorMsg);
                
                // Remove after 5 seconds
                setTimeout(() => {
                    errorMsg.remove();
                }, 5000);
            }
        }
    }
    
    // Update the orders display
    function updateOrdersDisplay(inProgressOrders, completedOrders) {
        // Check for new or removed in-progress orders
        updateOrdersSection(inProgressOrdersContainer, inProgressOrders, currentOrders.inProgress, 'in-progress');
        
        // Check for new or removed completed orders
        updateOrdersSection(completedOrdersContainer, completedOrders, currentOrders.completed, 'completed');
        
        // Update current orders for next comparison
        currentOrders.inProgress = [...inProgressOrders];
        currentOrders.completed = [...completedOrders];
        
        // إذا كان البحث نشطًا، قم بتحديث عرض الطلبيات بعد البحث
        if (isSearchActive) {
            updateOrdersDisplayAfterSearch();
        }
    }
    
    // Update a specific orders section (in-progress or completed) with performance optimizations
    function updateOrdersSection(container, newOrders, oldOrders, sectionType) {
        // Use Set for faster lookups
        const oldOrdersSet = new Set(oldOrders.map(order => order.orderNumber));
        const newOrdersSet = new Set(newOrders.map(order => order.orderNumber));
        
        // Find orders to add (new orders)
        const ordersToAdd = newOrders.filter(newOrder => !oldOrdersSet.has(newOrder.orderNumber));
        
        // Play sound for new in-progress orders or new completed orders (but not both at the same time)
        if (ordersToAdd.length > 0) {
            if (sectionType === 'in-progress') {
                // تشغيل الصوت فقط للطلبات الجديدة قيد التجهيز
                playNewOrderSound();
            } else if (sectionType === 'completed') {
                // تشغيل الصوت للطلبات المكتملة فقط إذا لم تكن موجودة سابقًا في قائمة قيد التجهيز
                // هذا يمنع تشغيل الصوت مرتين عند انتقال الطلب من قيد التجهيز إلى مكتمل
                const completedNotFromInProgress = ordersToAdd.filter(order => {
                    // التحقق مما إذا كان الطلب المكتمل ليس من الطلبات التي كانت قيد التجهيز
                    return !currentOrders.inProgress.some(inProgressOrder => 
                        inProgressOrder.orderNumber === order.orderNumber
                    );
                });
                
                if (completedNotFromInProgress.length > 0) {
                    playNewOrderSound();
                }
            }
        }
        
        // Find orders to remove (completed or cancelled)
        const ordersToRemove = oldOrders.filter(oldOrder => !newOrdersSet.has(oldOrder.orderNumber));
        
        // Batch DOM operations for better performance
        if (ordersToAdd.length > 0 || ordersToRemove.length > 0) {
            // Use requestAnimationFrame to optimize rendering
            requestAnimationFrame(() => {
                // Remove old orders
                if (ordersToRemove.length > 0) {
                    // Batch removals for better performance
                    const elementsToRemove = [];
                    
                    ordersToRemove.forEach(order => {
                        const orderElement = container.querySelector(`[data-order-number="${order.orderNumber}"]`);
                        if (orderElement) {
                            // Add fade-out animation
                            orderElement.classList.add('fade-out');
                            elementsToRemove.push(orderElement);
                        }
                    });
                    
                    // Remove after animation completes
                    if (elementsToRemove.length > 0) {
                        setTimeout(() => {
                            elementsToRemove.forEach(element => element.remove());
                        }, 500); // Match this with CSS animation duration
                    }
                }
                
                // Add new orders
                if (ordersToAdd.length > 0) {
                    // Create a document fragment to minimize DOM operations
                    const fragment = document.createDocumentFragment();
                    
                    ordersToAdd.forEach(order => {
                        const orderCard = createOrderCard(order, sectionType);
                        orderCard.classList.add('new-order');
                        fragment.appendChild(orderCard);
                    });
                    
                    // Append all new orders at once
                    container.appendChild(fragment);
                    
                    // Remove highlight after animation
                    setTimeout(() => {
                        const newOrderElements = container.querySelectorAll('.new-order');
                        newOrderElements.forEach(element => {
                            element.classList.remove('new-order');
                        });
                    }, 3000);
                }
                
                // Update existing orders if needed (e.g., time updates)
                const ordersToUpdate = newOrders.filter(newOrder => oldOrdersSet.has(newOrder.orderNumber));
                if (ordersToUpdate.length > 0) {
                    ordersToUpdate.forEach(newOrder => {
                        const existingOrder = oldOrders.find(o => o.orderNumber === newOrder.orderNumber);
                        if (existingOrder && existingOrder.time !== newOrder.time) {
                            const orderElement = container.querySelector(`[data-order-number="${newOrder.orderNumber}"]`);
                            if (orderElement) {
                                const timeElement = orderElement.querySelector('.order-time');
                                if (timeElement) {
                                    timeElement.textContent = newOrder.time;
                                }
                            }
                        }
                    });
                }
            });
        }
    }
    
    // Create an order card element with performance optimizations
    function createOrderCard(order, type) {
    console.log(`Creating card for type: ${type}, order number: ${order.orderNumber}, adding time: ${type !== 'completed'}, adding items: ${type === 'in-progress' && order.items && order.items.length > 0}`);
        // Use document fragment for better performance
        const fragment = document.createDocumentFragment();
        
        const card = document.createElement('div');
        card.className = 'order-card';
        card.dataset.orderNumber = order.orderNumber;
        
        // حساب وقت التجهيز المتوقع للطلبات قيد التجهيز
        let cardContent = `
            <div class="order-number">${order.orderNumber}</div>
        `;
        if (type !== 'completed') {
            cardContent += `<div class="order-time">${order.time}</div>`;
        }
        
        // إضافة وقت التجهيز المتوقع للطلبات قيد التجهيز فقط
        if (type === 'in-progress') {
            // استخدام وقت التحضير المحدد للمنتج أو الوقت الافتراضي
            const productPrepTime = order.preparationTime || preparationTimeMinutes;
            
            // إضافة وقت التجهيز إلى بطاقة الطلب
            cardContent += `<div class="expected-time">${productPrepTime} دقيقة</div>`;
            
            // Add progress indicator for visual feedback
            cardContent += `<div class="progress-indicator"></div>`;
        }
        
        // Add items count if available and in in-progress
        if (type === 'in-progress' && order.items && order.items.length > 0) {
            cardContent += `<div class="items-count">${order.items.length} صنف</div>`;
        }
        
        // Use innerHTML for faster DOM creation
        card.innerHTML = cardContent;
        
        fragment.appendChild(card);
        return fragment.firstChild;
    }
    
    // Auto-scroll to show new orders if needed with optimized performance
    function autoScrollToNewOrders() {
        if (document.hidden || isUserScrolling) return;
        
        const containers = [inProgressOrdersContainer, completedOrdersContainer];
        
        containers.forEach(container => {
            const newOrders = container.querySelectorAll('.new-order');
            if (newOrders.length > 0) {
                // Get the last new order
                const lastNewOrder = newOrders[newOrders.length - 1];
                
                // Check if it's out of view
                const containerRect = container.getBoundingClientRect();
                const orderRect = lastNewOrder.getBoundingClientRect();
                
                if (orderRect.bottom > containerRect.bottom || orderRect.top < containerRect.top) {
                    // Use requestAnimationFrame for smoother scrolling at 25fps
                    requestAnimationFrame(() => {
                        // Use scrollTo instead of scrollIntoView for better performance
                        const scrollTop = lastNewOrder.offsetTop - container.offsetTop - (containerRect.height / 2) + (orderRect.height / 2);
                        container.scrollTo({
                            top: scrollTop,
                            behavior: 'smooth'
                        });
                    });
                }
            }
        });
    }
    
    // Track user scrolling
    let isUserScrolling = false;
    let scrollTimeout;
    
    // Optimize scrolling performance
    function optimizeScrolling() {
        const containers = [inProgressOrdersContainer, completedOrdersContainer];
        
        containers.forEach(container => {
            // Throttle scroll events for better performance
            let scrollTimeout;
            container.addEventListener('scroll', () => {
                // Mark that user is actively scrolling
                isUserScrolling = true;
                clearTimeout(scrollTimeout);
                
                // Reset user scrolling flag after scrolling stops
                scrollTimeout = setTimeout(() => {
                    isUserScrolling = false;
                }, 1500); // Wait 1.5 seconds after scrolling stops
                
                // Add a class during scrolling to reduce animations
                container.classList.add('scrolling');
                
                // Remove the class after scrolling stops
                clearTimeout(container.dataset.scrollTimer);
                container.dataset.scrollTimer = setTimeout(() => {
                    container.classList.remove('scrolling');
                }, 100);
            }, { passive: true }); // Use passive listener for better performance
        });
    }
    
    // وظيفة البحث عن طلبية محددة
    function searchOrder() {
        const orderNumber = orderSearchInput.value.trim();
        
        if (!orderNumber) {
            // إذا كان حقل البحث فارغًا، أعد عرض جميع الطلبيات
            resetSearch();
            return;
        }
        
        // تحديث حالة البحث
        isSearchActive = true;
        searchedOrderNumber = orderNumber;
        
        // إخفاء جميع الطلبيات
        const allOrderCards = document.querySelectorAll('.order-card');
        allOrderCards.forEach(card => {
            const cardOrderNumber = card.dataset.orderNumber;
            if (cardOrderNumber === orderNumber) {
                card.classList.add('highlighted-order');
                card.style.display = 'flex';
                
                // التمرير إلى الطلبية المطلوبة
                setTimeout(() => {
                    card.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }, 100);
            } else {
                card.style.display = 'none';
            }
        });
        
        // إظهار رسالة إذا لم يتم العثور على الطلبية
        const orderFound = document.querySelector(`.order-card[data-order-number="${orderNumber}"]`);
        if (!orderFound) {
            showNotFoundMessage(orderNumber);
        } else {
            removeNotFoundMessage();
        }
    }
    
    // إعادة ضبط البحث وعرض جميع الطلبيات
    function resetSearch() {
        isSearchActive = false;
        searchedOrderNumber = null;
        orderSearchInput.value = '';
        
        // إظهار جميع الطلبيات
        const allOrderCards = document.querySelectorAll('.order-card');
        allOrderCards.forEach(card => {
            card.style.display = 'flex';
            card.classList.remove('highlighted-order');
        });
        
        // إزالة رسالة عدم العثور على الطلبية
        removeNotFoundMessage();
    }
    
    // إظهار رسالة عدم العثور على الطلبية
    function showNotFoundMessage(orderNumber) {
        removeNotFoundMessage();
        
        const message = document.createElement('div');
        message.className = 'not-found-message';
        message.innerHTML = `<p>لم يتم العثور على الطلبية رقم <strong>${orderNumber}</strong></p>
                            <button id="reset-search">عرض جميع الطلبيات</button>`;
        
        statusContainer.appendChild(message);
        
        // إضافة حدث النقر على زر إعادة الضبط
        document.getElementById('reset-search').addEventListener('click', resetSearch);
    }
    
    // إزالة رسالة عدم العثور على الطلبية
    function removeNotFoundMessage() {
        const message = document.querySelector('.not-found-message');
        if (message) {
            message.remove();
        }
    }
    
    // تحديث عرض الطلبيات بعد البحث
    function updateOrdersDisplayAfterSearch() {
        if (isSearchActive && searchedOrderNumber) {
            // إخفاء جميع الطلبيات ما عدا الطلبية المطلوبة
            const allOrderCards = document.querySelectorAll('.order-card');
            let orderFound = false;
            
            allOrderCards.forEach(card => {
                const cardOrderNumber = card.dataset.orderNumber;
                if (cardOrderNumber === searchedOrderNumber) {
                    card.style.display = 'flex';
                    card.classList.add('highlighted-order');
                    orderFound = true;
                } else {
                    card.style.display = 'none';
                }
            });
            
            // إظهار رسالة إذا لم يتم العثور على الطلبية
            if (!orderFound) {
                showNotFoundMessage(searchedOrderNumber);
            } else {
                removeNotFoundMessage();
            }
        }
    }
    
    // Initialize and set up polling
function initialize() {
    fetchConfig();
    fetchOrdersStatus();
    
    // Apply scrolling optimizations
    optimizeScrolling();
    
    // إضافة أحداث البحث
    searchButton.addEventListener('click', searchOrder);
    orderSearchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            searchOrder();
        }
    });
    
    // إضافة مستمعي الأحداث للبحث
    

    
    // استدعاء وظيفة التحقق من نوع المستخدم
    checkUserRole();
    
    // إعداد المسح التلقائي للطلبات المجهزة
    setupAutoRemoveCompletedOrders();
    
    // Start polling with default interval
    startPolling();
    
    // Add viewport visibility detection to pause animations when not visible
    document.addEventListener('visibilitychange', () => {
        const containers = [inProgressOrdersContainer, completedOrdersContainer];
        if (document.hidden) {
            containers.forEach(container => container.classList.add('page-hidden'));
            // Reduce polling frequency when page is hidden to save resources
            startPolling(15000); // 15 seconds when hidden
        } else {
            containers.forEach(container => container.classList.remove('page-hidden'));
            // Refresh data when page becomes visible again
            fetchOrdersStatus();
            // Restore normal polling frequency
            startPolling(5000); // 5 seconds when visible
        }
    });
    }
    
    // وظائف مسح الطلبات
    async function clearCompletedOrders() {
        if (confirm('هل أنت متأكد من مسح جميع الطلبات المكتملة؟ لا يمكن التراجع عن هذه العملية.')) {
            try {
                const response = await fetch('/api/clear_completed_orders', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                
                const data = await response.json();
                
                if (data.success) {
                    // عرض رسالة نجاح
                    const messageElement = document.createElement('div');
                    messageElement.className = 'success-message';
                    messageElement.textContent = data.message;
                    document.body.appendChild(messageElement);
                    
                    // إخفاء الرسالة بعد 3 ثوانٍ
                    setTimeout(() => {
                        messageElement.classList.add('fade-out');
                        setTimeout(() => {
                            document.body.removeChild(messageElement);
                        }, 500);
                    }, 3000);
                    
                    // تحديث عرض الطلبات
                    fetchOrdersStatus();
                } else {
                    alert(data.error || 'حدث خطأ أثناء مسح الطلبات المكتملة');
                }
            } catch (error) {
                console.error('Failed to clear completed orders:', error);
                alert('فشل الاتصال بالخادم');
            }
        }
    }
    

    
    // Variable polling interval
     let pollingInterval;
     function startPolling(interval = 5000) {
         // Clear any existing interval
         if (pollingInterval) {
             clearInterval(pollingInterval);
         }
         
         // Start new polling interval
         pollingInterval = setInterval(() => {
             fetchOrdersStatus();
             // Check for auto-scroll after data updates
             setTimeout(autoScrollToNewOrders, 100);
         }, interval);
     }
    
    // Play sound for new orders
    // استخدام متغير لتتبع آخر وقت تم فيه تشغيل الصوت لمنع التكرار
    let lastSoundPlayTime = 0;
    function playNewOrderSound() {
        const sound = document.getElementById('new-order-sound');
        const now = Date.now();
        // التحقق من أن الوقت المنقضي منذ آخر تشغيل للصوت أكثر من 3 ثوانٍ لمنع التكرار
        if (sound && !document.hidden && (now - lastSoundPlayTime > 3000)) {
            sound.currentTime = 0;
            sound.play().catch(error => {
                console.log('Error playing sound:', error);
            });
            // تحديث وقت آخر تشغيل للصوت
            lastSoundPlayTime = now;
        }
    }
    
    // وظيفة إعداد المسح التلقائي للطلبات المجهزة
    function setupAutoRemoveCompletedOrders() {
        // تنفيذ فحص كل دقيقة للطلبات المجهزة
        setInterval(() => {
            // الحصول على الوقت الحالي
            const now = new Date();
            
            // فحص كل طلب مجهز
            currentOrders.completed.forEach(order => {
                // استخراج وقت الطلب
                const [hours, minutes] = order.time.split(':').map(Number);
                const orderTime = new Date();
                orderTime.setHours(hours, minutes, 0);
                
                // حساب الفرق بالدقائق
                const diffMinutes = Math.floor((now - orderTime) / (1000 * 60));
                
                // إذا تجاوز الوقت المحدد، قم بمسح الطلب
                if (diffMinutes >= autoRemoveCompletedOrdersMinutes) {
                    // إزالة الطلب من واجهة المستخدم
                    const orderElement = completedOrdersContainer.querySelector(`[data-order-number="${order.orderNumber}"]`);
                    if (orderElement) {
                        orderElement.classList.add('fade-out');
                        setTimeout(() => {
                            orderElement.remove();
                        }, 500);
                    }
                    
                    // إزالة الطلب من القائمة الحالية
                    const index = currentOrders.completed.findIndex(o => o.orderNumber === order.orderNumber);
                    if (index !== -1) {
                        currentOrders.completed.splice(index, 1);
                    }
                    
                    // تحديث العداد
                    document.getElementById('completed-count').textContent = currentOrders.completed.length;
                }
            });
        }, 60000); // فحص كل دقيقة
    }
    
    // Start the application
    initialize();
    
    // For testing - simulate orders (remove in production)
    function simulateOrders() {
        // Sample data for testing
        const mockInProgress = Array.from({ length: Math.floor(Math.random() * 10) + 5 }, (_, i) => ({
            orderNumber: Math.floor(Math.random() * 100) + 1,
            time: `${Math.floor(Math.random() * 10) + 1}:${Math.floor(Math.random() * 60)}`,
        }));
        
        const mockCompleted = Array.from({ length: Math.floor(Math.random() * 15) + 10 }, (_, i) => ({
            orderNumber: Math.floor(Math.random() * 100) + 1,
            time: `${Math.floor(Math.random() * 10) + 1}:${Math.floor(Math.random() * 60)}`,
        }));
        
        updateOrdersDisplay(mockInProgress, mockCompleted);
    }
    
    // Uncomment for testing without backend
    // simulateOrders();
    // setInterval(simulateOrders, 8000);
});