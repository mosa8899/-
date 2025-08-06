document.addEventListener('DOMContentLoaded', () => {
    const productList = document.getElementById('product-list');
    const categoryContainer = document.getElementById('categories');
    const cartButton = document.getElementById('cart-button');
    const cartModal = document.getElementById('cart-modal');
    const closeModalButton = document.querySelector('.close-button');
    const cartCountSpan = document.getElementById('cart-count');
    const cartItemsContainer = document.getElementById('cart-items');
    const cartTotalSpan = document.getElementById('cart-total');
    const confirmOrderButton = document.getElementById('confirm-order-button');
    const qrCodeContainer = document.getElementById('qrcode');
    const restaurantNameH1 = document.getElementById('restaurant-name');

    // Product Detail Modal elements (NEW)
    const productDetailModal = document.getElementById('product-detail-modal');
    const closeProductDetailModalButton = document.getElementById('close-product-detail-modal');
    const productDetailName = document.getElementById('product-detail-name');
    const productDetailPrice = document.getElementById('product-detail-price');
    const qtyMinusBtn = document.getElementById('qty-minus-btn');
    const qtyDisplay = document.getElementById('qty-display');
    const qtyPlusBtn = document.getElementById('qty-plus-btn');
    const productDetailModifiers = document.getElementById('product-detail-modifiers');
    const addToCartFromDetailButton = document.getElementById('add-to-cart-from-detail');

    let allProducts = [];
    let cart = [];
    let currencySymbol = 'ريال';
    let currentProduct = null; // Product currently displayed in the detail modal
    
    // استرجاع السلة من التخزين المحلي عند تحميل الصفحة
    const savedCart = localStorage.getItem('cart');
    if (savedCart) {
        try {
            cart = JSON.parse(savedCart);
        } catch (e) {
            console.error('خطأ في استرجاع السلة من التخزين المحلي:', e);
            cart = [];
        }
    }

    async function fetchData() {
        try {
            const productsResponse = await fetch('/api/products');
            allProducts = await productsResponse.json();
            const configResponse = await fetch('/api/config');
            const config = await configResponse.json();
            currencySymbol = config.currency_symbol || 'ريال';
            restaurantNameH1.textContent = config.restaurant_name || 'قائمة الطعام';
            displayCategories();
            displayProducts();
        } catch (error) {
            console.error('Failed to fetch data:', error);
            productList.innerHTML = '<p>عفواً، حدث خطأ أثناء تحميل قائمة الطعام.</p>';
        }
    }

    function displayCategories() {
        const categories = ['الكل', ...new Set(allProducts.map(p => p.category).filter(Boolean))];
        categoryContainer.innerHTML = '';
        categories.forEach(category => {
            const button = document.createElement('button');
            button.className = 'category-button';
            button.textContent = category;
            if (category === 'الكل') button.classList.add('active');
            button.addEventListener('click', () => {
                filterByCategory(category);
                document.querySelectorAll('.category-button').forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');
            });
            categoryContainer.appendChild(button);
        });
    }

    function filterByCategory(category) {
        const filteredProducts = category === 'الكل' ? allProducts : allProducts.filter(p => p.category === category);
        displayProducts(filteredProducts);
    }

    function displayProducts(products = allProducts) {
        productList.innerHTML = '';
        products.forEach(product => {
            const card = document.createElement('div');
            card.className = 'product-card';
            // Note: The add-to-cart-button now opens the detail modal
            // إنشاء عنصر الوسائط (صورة أو فيديو) بناءً على وجود مسار فيديو للمنتج
            let mediaElement = '';
            if (product.video_path) {
                mediaElement = `
                    <video class="product-media" autoplay loop muted>
                        <source src="/api/product_video/${product.id}" type="video/mp4">
                        <img src="/api/product_image/${product.id}" alt="${product.name}" onerror="this.style.display='none'">
                    </video>
                `;
            } else {
                mediaElement = `<img src="/api/product_image/${product.id}" alt="${product.name}" onerror="this.style.display='none'">`;
            }
            
            card.innerHTML = `
                ${mediaElement}
                <div class="product-info">
                    <h3>${product.name}</h3>
                    <p class="price">${product.price.toFixed(2)} ${currencySymbol}</p>
                </div>
                <div class="product-actions">
                    <button class="add-to-cart-button" data-id="${product.id}">أضف إلى السلة</button>
                </div>
            `;
            productList.appendChild(card);
        });

        document.querySelectorAll('.add-to-cart-button').forEach(button => {
            button.addEventListener('click', (event) => {
                event.stopPropagation(); // Prevent any potential parent click events
                openProductDetail(parseInt(button.dataset.id));
            });
        });
    }

    // ---------------------- Product Detail Modal Logic (NEW) ----------------------
    function openProductDetail(productId) {
        currentProduct = allProducts.find(p => p.id === productId);
        if (!currentProduct) return;

        productDetailName.textContent = currentProduct.name;
        productDetailPrice.textContent = `${currentProduct.price.toFixed(2)} ${currencySymbol}`;
        qtyDisplay.textContent = '1'; // Reset quantity to 1

        // إضافة عرض الوسائط (صورة أو فيديو) في نافذة التفاصيل
        const productDetailMedia = document.getElementById('product-detail-media');
        if (productDetailMedia) {
            if (currentProduct.video_path) {
                productDetailMedia.innerHTML = `
                    <video class="product-detail-media" autoplay loop muted controls>
                        <source src="/api/product_video/${currentProduct.id}" type="video/mp4">
                        <img src="/api/product_image/${currentProduct.id}" alt="${currentProduct.name}" onerror="this.style.display='none'">
                    </video>
                `;
            } else {
                productDetailMedia.innerHTML = `<img class="product-detail-media" src="/api/product_image/${currentProduct.id}" alt="${currentProduct.name}" onerror="this.style.display='none'">`;
            }
        }

        productDetailModifiers.innerHTML = ''; // Clear previous modifiers
        if (currentProduct.modifiers && currentProduct.modifiers.length > 0) {
            currentProduct.modifiers.forEach(mod => {
                const label = document.createElement('label');
                // Use a unique data-id for modifiers in the checkbox
                label.innerHTML = `
                    <input type="checkbox" data-id="${mod.id}" data-price="${mod.price_change}"> 
                    <span>${mod.name}</span> 
                    <span class="mod-price">(+${mod.price_change.toFixed(2)} ${currencySymbol})</span>
                `;
                productDetailModifiers.appendChild(label);
            });
            // Remove the 'no modifiers' message if it exists
            productDetailModifiers.querySelector('.no-modifiers')?.remove(); 
        } else {
            productDetailModifiers.innerHTML = '<p class="no-modifiers">لا توجد إضافات متاحة لهذا المنتج.</p>';
        }

        productDetailModal.style.display = 'block';
    }

    qtyPlusBtn.addEventListener('click', () => {
        let currentQty = parseInt(qtyDisplay.textContent);
        qtyDisplay.textContent = Math.min(99, currentQty + 1); // Max quantity 99
    });

    qtyMinusBtn.addEventListener('click', () => {
        let currentQty = parseInt(qtyDisplay.textContent);
        qtyDisplay.textContent = Math.max(1, currentQty - 1); // Min quantity 1
    });

    addToCartFromDetailButton.addEventListener('click', () => {
        if (!currentProduct) return;

        const quantity = parseInt(qtyDisplay.textContent);
        const selectedModifiers = [];
        productDetailModifiers.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
            const modId = parseInt(checkbox.dataset.id);
            // Find the full modifier object from the current product's modifiers
            const modifier = currentProduct.modifiers.find(m => m.id === modId);
            if (modifier) {
                selectedModifiers.push({
                    id: modifier.id,
                    name: modifier.name,
                    price_change: modifier.price_change
                });
            }
        });

        // Generate a unique identifier for the item in cart, including modifiers
        // This is crucial to treat "Burger with Cheese" as different from "Burger without Cheese"
        const uniqueId = `${currentProduct.id}-${selectedModifiers.map(m => m.id).sort().join('-')}`;
        
        const existingCartItem = cart.find(item => item.uniqueId === uniqueId);

        if (existingCartItem) {
            existingCartItem.qty += quantity;
        } else {
            const basePrice = currentProduct.price;
            const modifiersTotal = selectedModifiers.reduce((sum, mod) => sum + mod.price_change, 0);
            const finalPricePerUnit = basePrice + modifiersTotal;

            // إضافة المنتج إلى السلة مع تأثير بصري
            cart.push({
                uniqueId: uniqueId, // Used for internal cart management (adding/removing same item+mods)
                id: currentProduct.id, // Actual product ID for backend
                name: currentProduct.name,
                basePrice: basePrice, // Store base price for display or future reference
                price: finalPricePerUnit, // This is the total price per unit (base + modifiers)
                qty: quantity,
                modifiers: selectedModifiers, // Store selected modifiers' full details
                isNew: true // علامة للعناصر الجديدة لإظهار تأثير بصري
            });
            
            // عرض تأثير بصري للإضافة
            showAddToCartAnimation(currentProduct.id);
        }
        updateCart();
        productDetailModal.style.display = 'none'; // Close the detail modal
    });

    closeProductDetailModalButton.addEventListener('click', () => {
        productDetailModal.style.display = 'none';
        currentProduct = null;
    });

    // Close modal if click outside content
    window.addEventListener('click', (e) => {
        if (e.target == productDetailModal) {
            productDetailModal.style.display = 'none';
            currentProduct = null;
        }
    });

    // ---------------------- Cart Logic (Modified to handle uniqueId and modifiers) ----------------------
    function updateCart() {
        cart = cart.filter(item => item.qty > 0);
        cartItemsContainer.innerHTML = '';
        let total = 0;
        let count = 0;

        cart.forEach(item => {
            const itemElement = document.createElement('div');
            itemElement.className = 'cart-item';
            
            // إضافة صنف للعناصر الجديدة لإظهار تأثير بصري
            if (item.isNew) {
                itemElement.classList.add('new-item');
                // إزالة علامة العنصر الجديد بعد إظهار التأثير
                setTimeout(() => {
                    item.isNew = false;
                    itemElement.classList.remove('new-item');
                }, 1000);
            }
            
            let itemDetails = `<span>${item.name} (${item.qty})</span>`;
            if (item.modifiers && item.modifiers.length > 0) {
                const modNames = item.modifiers.map(m => m.name).join(', ');
                itemDetails += `<small style="font-size:0.8em; color:#666; display:block;">(${modNames})</small>`;
            }

            itemElement.innerHTML = `
                ${itemDetails}
                <span class="item-controls">
                    <button class="plus" data-id="${item.uniqueId}">+</button>
                    <button class="minus" data-id="${item.uniqueId}">-</button>
                </span>
                <span>${(item.price * item.qty).toFixed(2)} ${currencySymbol}</span>
            `;
            cartItemsContainer.appendChild(itemElement);
            total += item.price * item.qty;
            count += item.qty;
        });

        cartTotalSpan.textContent = `${total.toFixed(2)} ${currencySymbol}`;
        cartCountSpan.textContent = count;

        // Use uniqueId for quantity controls in cart
        document.querySelectorAll('.cart-item .plus').forEach(b => b.onclick = () => updateCartItemQuantity(b.dataset.id, 1));
        document.querySelectorAll('.cart-item .minus').forEach(b => b.onclick = () => updateCartItemQuantity(b.dataset.id, -1));
        
        // حفظ السلة في التخزين المحلي
        localStorage.setItem('cart', JSON.stringify(cart));
    }

    function updateCartItemQuantity(uniqueId, change) {
        const item = cart.find(i => i.uniqueId === uniqueId);
        if (item) {
            item.qty += change;
            updateCart();
            // حفظ السلة في التخزين المحلي
            localStorage.setItem('cart', JSON.stringify(cart));
        }
    }


    confirmOrderButton.addEventListener('click', async () => {
        if (cart.length === 0) {
            alert('سلتك فارغة!');
            return;
        }
    
        const orderData = {
            source: 'WebApp',
            items: cart.map(item => ({
                id: item.id, // This is the original product ID
                qty: item.qty,
                modifiers: item.modifiers ? item.modifiers.map(mod => mod.id) : [] // Send only modifier IDs back to backend
            }))
        };
    
        confirmOrderButton.disabled = true;
        confirmOrderButton.textContent = 'جاري إنشاء الرمز...';
    
        try {
            const response = await fetch('/api/create_temp_order', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(orderData),
            });
    
            if (!response.ok) throw new Error(`Server error: ${response.statusText}`);
    
            const result = await response.json();
            const orderId = result.order_id;

            document.getElementById('checkout-section').style.display = 'none';
            document.getElementById('qr-code-section').style.display = 'block';
            qrCodeContainer.innerHTML = '';
            new QRCode(qrCodeContainer, { text: orderId, width: 256, height: 256, correctLevel: QRCode.CorrectLevel.H });
            
            // مسح السلة بعد تأكيد الطلب بنجاح
            cart = [];
            updateCart();
            localStorage.removeItem('cart');
    
        } catch (error) {
            console.error('Failed to create temporary order:', error);
            alert('عفواً، حدث خطأ في الاتصال بالخادم. يرجى المحاولة مرة أخرى.');
            // Restore the button and view
            document.getElementById('checkout-section').style.display = 'block';
            document.getElementById('qr-code-section').style.display = 'none';
        } finally {
            confirmOrderButton.disabled = false;
            confirmOrderButton.textContent = '✅ تأكيد الطلب وإنشاء الرمز';
        }
    });

    // Original cart button and modal closing logic
    cartButton.addEventListener('click', () => {
        document.getElementById('checkout-section').style.display = 'block';
        document.getElementById('qr-code-section').style.display = 'none';
        qrCodeContainer.innerHTML = ''; // Clear QR if visible
        cartModal.style.display = 'block';
    });
    closeModalButton.addEventListener('click', () => cartModal.style.display = 'none');
    window.addEventListener('click', (e) => {
        if (e.target == cartModal) cartModal.style.display = 'none'
    });
    
    // دالة لإظهار تأثير بصري عند إضافة منتج إلى السلة
    function showAddToCartAnimation(productId) {
        // العثور على بطاقة المنتج
        const productCard = document.querySelector(`.add-to-cart-button[data-id="${productId}"]`).closest('.product-card');
        if (!productCard) return;
        
        // تشغيل صوت إضافة المنتج
        playAddToCartSound();
        
        // إنشاء عنصر الرسوم المتحركة
        const animElement = document.createElement('div');
        animElement.className = 'add-to-cart-animation';
        animElement.innerHTML = '<span>+1</span>';
        productCard.appendChild(animElement);
        
        // تحريك العنصر نحو زر السلة
        setTimeout(() => {
            const cartButton = document.getElementById('cart-button');
            const cartRect = cartButton.getBoundingClientRect();
            const animRect = animElement.getBoundingClientRect();
            
            // حساب المسافة للتحريك
            const moveX = cartRect.left - animRect.left + (cartRect.width / 2) - (animRect.width / 2);
            const moveY = cartRect.top - animRect.top + (cartRect.height / 2) - (animRect.height / 2);
            
            // تطبيق التحريك
            animElement.style.transform = `translate(${moveX}px, ${moveY}px) scale(0.5)`;
            animElement.style.opacity = '0';
            
            // إضافة تأثير نبض لزر السلة
            cartButton.classList.add('cart-pulse');
            
            // إزالة عنصر الرسوم المتحركة بعد انتهاء التأثير
            setTimeout(() => {
                animElement.remove();
                cartButton.classList.remove('cart-pulse');
            }, 500);
        }, 100);
    }
    
    // إضافة صوت عند إضافة منتج إلى السلة
    const addToCartSound = new Audio('/static/sounds/add-to-cart.mp3');
    addToCartSound.volume = 0.5; // ضبط مستوى الصوت
    
    // دالة لتشغيل الصوت عند إضافة منتج
    function playAddToCartSound() {
        addToCartSound.currentTime = 0; // إعادة تعيين الصوت للبداية
        addToCartSound.play().catch(e => console.error('فشل تشغيل الصوت:', e));
    }
    
    // Initial fetch of data when the page loads
    fetchData();
});