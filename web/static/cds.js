document.addEventListener('DOMContentLoaded', () => {
    // العناصر الرئيسية
    const restaurantNameH1 = document.getElementById('restaurant-name');
    const preparingOrdersList = document.getElementById('preparing-orders');
    const readyOrdersList = document.getElementById('ready-orders');
    const mediaContent = document.getElementById('media-content');
    const welcomeMessage = document.getElementById('welcome-message');
    const newOrderSound = document.getElementById('new-order-sound');
    const mainContainer = document.querySelector('.main-container');
    
    // إضافة تأثير الخلفية المتحركة
    createBackgroundEffect();
    
    // متغيرات لتتبع الطلبات
    let preparingOrders = {};
    let readyOrders = {};
    let config = {};
    let preparationTimeMinutes = 10; // وقت التحضير الافتراضي
    
    // مدة بقاء الطلب في قائمة الجاهز (بالمللي ثانية)
    let orderTimeout = 50 * 60 * 1000; // 50 دقيقة افتراضيًا
    
    // إنشاء تأثير الخلفية المتحركة
    function createBackgroundEffect() {
        const bgEffect = document.createElement('div');
        bgEffect.className = 'background-effect';
        document.body.appendChild(bgEffect);
        
        for (let i = 0; i < 20; i++) {
            const particle = document.createElement('div');
            particle.className = 'particle';
            particle.style.left = `${Math.random() * 100}%`;
            particle.style.top = `${Math.random() * 100}%`;
            particle.style.animationDuration = `${Math.random() * 20 + 10}s`;
            particle.style.animationDelay = `${Math.random() * 5}s`;
            bgEffect.appendChild(particle);
        }
    }
    
    // تحميل إعدادات المطعم
    async function fetchConfig() {
        try {
            const response = await fetch('/api/config');
            config = await response.json();
            
            // تحديث اسم المطعم مع تأثير الكتابة
            typeWriterEffect(restaurantNameH1, config.restaurant_name || 'مطعمنا');
            
            // تحديث مدة بقاء الطلب
            if (config.customer_display_timeout_minutes) {
                orderTimeout = config.customer_display_timeout_minutes * 60 * 1000;
            }
            
            // تحديث وقت التحضير
            if (config.preparation_time_minutes) {
                preparationTimeMinutes = config.preparation_time_minutes;
            }
            
            // تحديث رسالة الترحيب مع تأثير الظهور التدريجي
            if (config.customer_display_promo_message) {
                fadeInEffect(welcomeMessage, config.customer_display_promo_message);
            } else {
                fadeInEffect(welcomeMessage, 'أهلاً وسهلاً بكم في مطعمنا');
            }
            
            // تحميل الوسائط إذا كانت متوفرة
            loadMedia();
            
            // إضافة تأثير الساعة الرقمية
            addDigitalClock();
            
        } catch (error) {
            console.error('فشل في تحميل إعدادات المطعم:', error);
        }
    }
    
    // تأثير الكتابة
    function typeWriterEffect(element, text) {
        element.textContent = '';
        let i = 0;
        const speed = 100; // سرعة الكتابة
        
        function type() {
            if (i < text.length) {
                element.textContent += text.charAt(i);
                i++;
                setTimeout(type, speed);
            }
        }
        
        type();
    }
    
    // تأثير الظهور التدريجي
    function fadeInEffect(element, text) {
        element.style.opacity = 0;
        element.textContent = text;
        
        let opacity = 0;
        const fadeInterval = setInterval(() => {
            if (opacity < 1) {
                opacity += 0.1;
                element.style.opacity = opacity;
            } else {
                clearInterval(fadeInterval);
            }
        }, 100);
    }
    
    // إضافة ساعة رقمية
    function addDigitalClock() {
        const header = document.querySelector('header');
        const clockDiv = document.createElement('div');
        clockDiv.className = 'digital-clock';
        header.appendChild(clockDiv);
        
        function updateClock() {
            const now = new Date();
            const timeString = now.toLocaleTimeString('ar-SA');
            clockDiv.textContent = timeString;
        }
        
        updateClock();
        setInterval(updateClock, 1000);
    }
    
    // تحميل الوسائط (صورة أو فيديو)
    function loadMedia() {
        if (!config.cds_media_path) {
            console.log('لا يوجد مسار وسائط محدد');
            return;
        }
        
        // إزالة رسالة الترحيب
        welcomeMessage.style.display = 'none';
        
        const mediaPath = config.cds_media_path;
        const fileExtension = mediaPath.split('.').pop().toLowerCase();
        const mediaContent = document.querySelector('.media-content');
        
        // تحديد نوع الملف
        const videoFormats = ['mp4', 'webm', 'ogg', 'avi', 'mov'];
        const imageFormats = ['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg'];
        
        if (videoFormats.includes(fileExtension)) {
            // إنشاء عنصر فيديو
            const video = document.createElement('video');
            video.src = mediaPath;
            video.autoplay = true;
            video.loop = true;
            video.muted = true;
            video.controls = false;
            video.style.width = '100%';
            video.style.height = '100%';
            video.style.objectFit = 'contain';
            
            // إضافة معالج الأخطاء
            video.onerror = function() {
                console.log('فشل في تحميل الفيديو:', mediaPath);
                mediaContent.innerHTML = '<div style="color: #666; font-size: 1.2rem;">لا توجد وسائط متاحة</div>';
            };
            
            // إضافة معالج التحميل الناجح
            video.onloadeddata = function() {
                console.log('تم تحميل الفيديو بنجاح:', mediaPath);
            };
            
            // إضافة الفيديو إلى المحتوى
            mediaContent.innerHTML = '';
            mediaContent.appendChild(video);
            
            // إضافة overlay للفيديو (اختياري)
            const overlay = document.createElement('div');
            overlay.className = 'video-overlay';
            overlay.textContent = 'فيديو ترحيبي';
            mediaContent.appendChild(overlay);
            
        } else if (imageFormats.includes(fileExtension)) {
            // إنشاء عنصر صورة
            const img = document.createElement('img');
            img.src = mediaPath;
            img.alt = 'صورة ترحيبية';
            img.style.maxWidth = '100%';
            img.style.maxHeight = '100%';
            img.style.objectFit = 'contain';
            
            // إضافة معالج الأخطاء
            img.onerror = function() {
                console.log('فشل في تحميل الصورة:', mediaPath);
                mediaContent.innerHTML = '<div style="color: #666; font-size: 1.2rem;">لا توجد وسائط متاحة</div>';
            };
            
            // إضافة معالج التحميل الناجح
            img.onload = function() {
                console.log('تم تحميل الصورة بنجاح:', mediaPath);
            };
            
            // إضافة الصورة إلى المحتوى
            mediaContent.innerHTML = '';
            mediaContent.appendChild(img);
        } else {
            console.log('نوع ملف غير مدعوم:', fileExtension);
            mediaContent.innerHTML = '<div style="color: #666; font-size: 1.2rem;">نوع ملف غير مدعوم</div>';
        }
    }
    
    // جلب حالة الطلبات
    async function fetchOrdersStatus() {
        try {
            const response = await fetch('/api/orders_status');
            const data = await response.json();
            
            // تحديث الطلبات قيد التجهيز (الطلبات المدفوعة)
            updatePreparingOrders(data.inProgress);
            
            // تحديث الطلبات الجاهزة (الطلبات المكتملة)
            updateReadyOrders(data.completed);
            
        } catch (error) {
            console.error('فشل في جلب حالة الطلبات:', error);
        }
    }
    
    // تحديث قائمة الطلبات قيد التجهيز
    function updatePreparingOrders(orders) {
        // تتبع الطلبات الجديدة
        const newOrders = [];
        
        // تحديث الطلبات الموجودة وإضافة الجديدة
        orders.forEach(order => {
            const orderNumber = order.daily_order_number;
            
            // إذا كان الطلب جديدًا
            if (!preparingOrders[orderNumber]) {
                // إنشاء عنصر الطلب
                const orderItem = document.createElement('div');
                orderItem.className = 'order-item preparing-item new-order';
                
                // إنشاء رقم الطلب بخط كبير
                const orderNumberElement = document.createElement('div');
                orderNumberElement.className = 'order-number';
                orderNumberElement.textContent = orderNumber;
                
                // إضافة وقت الطلب
                const orderTimeElement = document.createElement('div');
                orderTimeElement.className = 'order-time';
                
                // تحويل وقت الطلب إلى كائن Date
                const orderTime = order.time ? order.time : new Date().toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
                orderTimeElement.textContent = `الوقت: ${orderTime}`;
                
                // إضافة وقت التحضير المتوقع
                const estimatedTimeElement = document.createElement('div');
                estimatedTimeElement.className = 'estimated-time';
                
                // استخدام وقت التحضير المحدد للمنتج أو الوقت الافتراضي
                const productPrepTime = order.preparationTime || preparationTimeMinutes;
                estimatedTimeElement.textContent = `${productPrepTime} دقيقة`;
                estimatedTimeElement.style.fontSize = '1.1rem';
                
                // إضافة قائمة المنتجات مع الصور
                if (order.items && order.items.length > 0) {
                    const itemsList = document.createElement('div');
                    itemsList.className = 'order-items-list';
                    
                    order.items.forEach((item, index) => {
                        const itemDetail = document.createElement('div');
                        itemDetail.className = 'order-item-detail new-item';
                        
                        itemDetail.innerHTML = `
                            <img src="/api/product_image/${item.product_id}" alt="${item.name}" onerror="this.style.display='none'">
                            <span class="item-name">${item.name}</span>
                            <span class="item-quantity">×${item.quantity}</span>
                        `;
                        
                        // إضافة تأخير تدريجي لكل عنصر للحصول على تأثير متتابع
                        setTimeout(() => {
                            itemsList.appendChild(itemDetail);
                            
                            // إزالة صنف العنصر الجديد بعد انتهاء التأثير
                            setTimeout(() => {
                                itemDetail.classList.remove('new-item');
                            }, 1000);
                        }, index * 100);
                    });
                    
                    orderItem.appendChild(orderNumberElement);
                    orderItem.appendChild(orderTimeElement);
                    orderItem.appendChild(itemsList);
                    orderItem.appendChild(estimatedTimeElement);
                } else {
                    // إضافة العناصر إلى عنصر الطلب (الطريقة القديمة)
                    orderItem.appendChild(orderNumberElement);
                    orderItem.appendChild(orderTimeElement);
                    orderItem.appendChild(estimatedTimeElement);
                }
                
                // إضافة تأثير النبض للطلبات الجديدة
                orderItem.dataset.orderNumber = orderNumber;
                
                // إضافة الطلب إلى القائمة
                preparingOrdersList.appendChild(orderItem);
                
                // تخزين الطلب في المتغير
                preparingOrders[orderNumber] = {
                    element: orderItem,
                    data: order,
                    addedAt: Date.now()
                };
                
                // إضافة الطلب إلى قائمة الطلبات الجديدة
                newOrders.push(orderNumber);
            }
        });
        
        // تشغيل صوت للطلبات الجديدة
        if (newOrders.length > 0 && newOrderSound) {
            newOrderSound.play().catch(e => console.error('فشل تشغيل الصوت:', e));
        }
        
        // إزالة الطلبات التي لم تعد قيد التجهيز
        Object.keys(preparingOrders).forEach(orderNumber => {
            const orderExists = orders.some(order => order.daily_order_number == orderNumber);
            if (!orderExists) {
                // إزالة العنصر من DOM
                preparingOrders[orderNumber].element.remove();
                
                // إزالة الطلب من المتغير
                delete preparingOrders[orderNumber];
            }
        });
    }
    
    // تحديث قائمة الطلبات الجاهزة
    function updateReadyOrders(orders) {
        // تتبع الطلبات الجديدة
        const newOrders = [];
        
        // تحديث الطلبات الموجودة وإضافة الجديدة
        orders.forEach(order => {
            const orderNumber = order.daily_order_number;
            
            // إذا كان الطلب جديدًا في قائمة الجاهزة
            if (!readyOrders[orderNumber]) {
                // إنشاء عنصر الطلب
                const orderItem = document.createElement('div');
                orderItem.className = 'order-item ready-item new-order';
                
                // إنشاء رقم الطلب بخط كبير
                const orderNumberElement = document.createElement('div');
                orderNumberElement.className = 'order-number';
                orderNumberElement.textContent = orderNumber;
                
                // إضافة وقت الطلب
                const orderTimeElement = document.createElement('div');
                orderTimeElement.className = 'order-time';
                
                // تحويل وقت الطلب إلى كائن Date
                const orderTime = order.time ? order.time : new Date().toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' });
                orderTimeElement.textContent = `الوقت: ${orderTime}`;
                
                // إضافة رسالة جاهز للاستلام
                const readyMessageElement = document.createElement('div');
                readyMessageElement.className = 'ready-message';
                readyMessageElement.textContent = 'جاهز للاستلام';
                
                // إضافة قائمة المنتجات مع الصور
                if (order.items && order.items.length > 0) {
                    const itemsList = document.createElement('div');
                    itemsList.className = 'order-items-list';
                    
                    order.items.forEach((item, index) => {
                        const itemDetail = document.createElement('div');
                        itemDetail.className = 'order-item-detail new-item';
                        
                        itemDetail.innerHTML = `
                            <img src="/api/product_image/${item.product_id}" alt="${item.name}" onerror="this.style.display='none'">
                            <span class="item-name">${item.name}</span>
                            <span class="item-quantity">×${item.quantity}</span>
                        `;
                        
                        // إضافة تأخير تدريجي لكل عنصر للحصول على تأثير متتابع
                        setTimeout(() => {
                            itemsList.appendChild(itemDetail);
                            
                            // إزالة صنف العنصر الجديد بعد انتهاء التأثير
                            setTimeout(() => {
                                itemDetail.classList.remove('new-item');
                            }, 1000);
                        }, index * 100);
                    });
                    
                    orderItem.appendChild(orderNumberElement);
                    orderItem.appendChild(orderTimeElement);
                    orderItem.appendChild(itemsList);
                    orderItem.appendChild(readyMessageElement);
                } else {
                    // إضافة العناصر إلى عنصر الطلب (الطريقة القديمة)
                    orderItem.appendChild(orderNumberElement);
                    orderItem.appendChild(orderTimeElement);
                    orderItem.appendChild(readyMessageElement);
                }
                
                // إضافة تأثير النبض للطلبات الجديدة
                orderItem.dataset.orderNumber = orderNumber;
                
                // إضافة الطلب إلى القائمة
                readyOrdersList.appendChild(orderItem);
                
                // تخزين الطلب في المتغير
                readyOrders[orderNumber] = {
                    element: orderItem,
                    data: order,
                    addedAt: Date.now()
                };
                
                // إضافة تأثير انتقالي عند نقل الطلب من قيد التجهيز إلى جاهز
                if (preparingOrders[orderNumber]) {
                    const preparingItem = preparingOrders[orderNumber].element;
                    preparingItem.classList.add('moving-out');
                    
                    setTimeout(() => {
                        preparingItem.remove();
                        delete preparingOrders[orderNumber];
                    }, 500);
                }
                
                // إضافة الطلب إلى قائمة الطلبات الجديدة
                newOrders.push(orderNumber);
                
                // جدولة إزالة الطلب بعد المدة المحددة
                setTimeout(() => {
                    removeReadyOrder(orderNumber);
                }, orderTimeout);
            }
        });
        
        // تشغيل صوت للطلبات الجديدة
        if (newOrders.length > 0 && newOrderSound) {
            newOrderSound.play().catch(e => console.error('فشل تشغيل الصوت:', e));
        }
    }
    
    // إزالة طلب من قائمة الجاهزة
    function removeReadyOrder(orderNumber) {
        if (readyOrders[orderNumber]) {
            // إزالة العنصر من DOM
            readyOrders[orderNumber].element.remove();
            
            // إزالة الطلب من المتغير
            delete readyOrders[orderNumber];
        }
    }
    
    // تحسين الأداء عند عدم ظهور الصفحة
    let isPageVisible = true;
    let pollingInterval;
    
    // تحديد فترة التحديث بناءً على حالة ظهور الصفحة
    function setupPolling() {
        // إلغاء الفاصل الزمني الحالي إذا كان موجودًا
        if (pollingInterval) {
            clearInterval(pollingInterval);
        }
        
        // تعيين فاصل زمني جديد
        const interval = isPageVisible ? 3000 : 10000; // 3 ثوانٍ عند الظهور، 10 ثوانٍ عند الإخفاء
        pollingInterval = setInterval(fetchOrdersStatus, interval);
    }
    
    // مراقبة حالة ظهور الصفحة
    document.addEventListener('visibilitychange', () => {
        isPageVisible = document.visibilityState === 'visible';
        setupPolling();
    });
    
    // بدء التطبيق
    fetchConfig();
    fetchOrdersStatus();
    setupPolling();
});