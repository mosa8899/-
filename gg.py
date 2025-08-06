import sys
import os
import sqlite3
import json
import random
import string
import qrcode
import subprocess
import base64
import urllib.request
import urllib.error
import requests
from datetime import datetime, date

# --- استيراد مكتبات الواجهة والكاميرا والفيديو ---
import cv2
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QPushButton, QLabel, QLineEdit, QMessageBox, QFrame,
                             QDialog, QTextEdit, QCalendarWidget, QFileDialog,
                             QComboBox, QTabWidget, QGridLayout, QDoubleSpinBox,
                             QTableWidget, QTableWidgetItem, QHeaderView, QListWidget,
                             QListWidgetItem, QCheckBox, QDialogButtonBox, QRadioButton, QButtonGroup,
                             QSizePolicy, QStackedWidget, QFormLayout, QSpinBox, QGroupBox,
                             QInputDialog, QScrollArea, QMenu)
from PySide6.QtGui import QFont, QIcon, QPixmap, QScreen, QPalette, QColor, QPainter, QAction
from PySide6.QtCore import (Qt, QThread, Signal as pyqtSignal, QTimer, QSize, QUrl, QBuffer, QIODevice,
                            QPropertyAnimation, QEasingCurve, QPauseAnimation, QSequentialAnimationGroup, QByteArray)
from PySide6.QtMultimedia import QSoundEffect, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget

# --- استيراد مكتبات الطباعة ---
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.pagesizes import letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# --- استيراد مكتبة الطباعة المحسنة لـ Windows ---
try:
    import win32print
    import win32api
    WINDOWS_PRINT_SUPPORT = True
except ImportError:
    WINDOWS_PRINT_SUPPORT = False

# --- استيراد مكتبات التقارير المتقدمة ---
try:
    import pandas as pd
    import matplotlib
    matplotlib.use('QtAgg')
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
    import seaborn as sns
    ADVANCED_REPORTS_SUPPORT = True
except ImportError:
    ADVANCED_REPORTS_SUPPORT = False

# --- استيراد مكتبات حل مشكلة اللغة العربية ---
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SUPPORT = True
except ImportError:
    ARABIC_SUPPORT = False

# --- استيراد مكتبة مسح الباركود المحسنة ---
try:
    from pyzbar import pyzbar
    PYZBAR_SUPPORT = True
except ImportError:
    PYZBAR_SUPPORT = False

# --- استيراد مكتبات الخادم والشبكات ---
try:
    from flask import Flask, jsonify, render_template, send_from_directory, request
    import threading
    import socket
    WEB_SERVER_SUPPORT = True
except ImportError:
    WEB_SERVER_SUPPORT = False


# ==============================================================================
# --- قسم الخادم: واجهة برمجة المنيو الرقمي ---
# ==============================================================================

if WEB_SERVER_SUPPORT:
    # إنشاء تطبيق فلاسك العالمي
    flask_app = Flask(__name__, template_folder='web/templates', static_folder='web/static')
    
    # قاموس عالمي لتخزين الطلبات المؤقتة
    temp_orders = {}

    # تعطيل تسجيلات فلاسك لتبقى الواجهة نظيفة
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    
    @flask_app.route('/')
    def menu_home():
        """يعرض صفحة المنيو الرئيسية"""
        return render_template('menu.html')
        
    @flask_app.route('/orders-status')
    def orders_status_page():
        """يعرض صفحة حالة الطلبات للعملاء"""
        return render_template('orders_status.html')

    @flask_app.route('/api/config')
    def get_app_config():
        """يرسل إعدادات المطعم الأساسية للمنيو الرقمي"""
        config = load_config()
        return jsonify({
            'restaurant_name': config.get('restaurant_name', 'مطعمي'),
            'currency_symbol': config.get('currency_symbol', 'ريال'),
            'preparation_time_minutes': config.get('preparation_time_minutes', 10),
            'customer_display_timeout_minutes': config.get('customer_display_timeout_minutes', 30),
            'cds_media_path': config.get('cds_media_path', ''),
            'auto_remove_completed_orders_minutes': config.get('auto_remove_completed_orders_minutes', 20)
        })

    @flask_app.route('/api/products')
    def get_products():
        """يرسل قائمة المنتجات المتاحة كبيانات JSON مع الإضافات المرتبطة بها فقط"""
        try:
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            
            # التحقق من وجود عمود video_path
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(products)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'video_path' in columns:
                products_db = conn.execute("SELECT id, name, price, category, video_path FROM products WHERE is_available = 1").fetchall()
            else:
                products_db = conn.execute("SELECT id, name, price, category FROM products WHERE is_available = 1").fetchall()
            
            products_list = []
            for p in products_db:
                product_data = dict(p)
                # جلب الإضافات المرتبطة بالمنتج
                modifiers_db = conn.execute("""
                    SELECT m.id, m.name, m.price_change 
                    FROM modifiers m
                    JOIN product_modifier_links l ON m.id = l.modifier_id
                    WHERE l.product_id = ?
                """, (p['id'],)).fetchall()
                
                product_data['modifiers'] = [dict(mod) for mod in modifiers_db]
                products_list.append(product_data)
            
            conn.close()
            return jsonify(products_list)
        except Exception as e:
            print(f"[Flask Error] get_products: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route('/api/product_image/<int:product_id>')
    def get_product_image(product_id):
        """يرسل صورة المنتج إذا كانت موجودة"""
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            path_result = cursor.execute("SELECT image_path, video_path FROM products WHERE id = ?", (product_id,)).fetchone()
            conn.close()
            
            # التحقق من وجود مسار الصورة وإرسالها
            if path_result and path_result[0] and os.path.exists(path_result[0]):
                abs_path = os.path.abspath(path_result[0])
                # السماح بالوصول إلى الملفات خارج مجلد المشروع مع التحقق من أنها ملفات صور آمنة
                if not os.path.exists(abs_path) or not any(abs_path.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']):
                    print(f"[Flask Warning] Unsafe image path: {abs_path}")
                    return send_from_directory('web/static', 'default.png')
                directory, filename = os.path.split(abs_path)
                return send_from_directory(directory, filename)
            else:
                return send_from_directory('web/static', 'default.png')
        except Exception as e:
            print(f"[Flask Error] get_product_image: {e}")
            return send_from_directory('web/static', 'default.png')
            
    @flask_app.route('/api/product_video/<int:product_id>')
    def get_product_video(product_id):
        """يرسل فيديو المنتج إذا كان موجوداً"""
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            path_result = cursor.execute("SELECT video_path FROM products WHERE id = ?", (product_id,)).fetchone()
            conn.close()
            
            # التحقق من وجود مسار الفيديو وإرساله
            if path_result and path_result[0] and os.path.exists(path_result[0]):
                abs_path = os.path.abspath(path_result[0])
                # السماح بالوصول إلى الملفات خارج مجلد المشروع مع التحقق من أنها ملفات فيديو آمنة
                if not os.path.exists(abs_path) or not any(abs_path.lower().endswith(ext) for ext in ['.mp4', '.webm', '.ogg', '.mov', '.avi', '.mkv']):
                    print(f"[Flask Warning] Unsafe video path: {abs_path}")
                    return jsonify({"error": "Video not found or invalid format"}), 404
                directory, filename = os.path.split(abs_path)
                return send_from_directory(directory, filename)
            else:
                return jsonify({"error": "Video not found"}), 404
        except Exception as e:
            print(f"[Flask Error] get_product_video: {e}")
            return jsonify({"error": str(e)}), 500

    @flask_app.route('/api/create_temp_order', methods=['POST'])
    def create_temp_order():
        """يستقبل طلب من الويب، يخزنه مؤقتاً، ويعيد معرفاً قصيراً."""
        order_data = request.get_json()
        if not order_data or 'items' not in order_data:
            return jsonify({"error": "Invalid order data"}), 400
        
        # إنشاء معرف فريد وقصير
        order_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        while order_id in temp_orders:
            order_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            
        # تخزين الطلب مع طابع زمني لاحتمالية التنظيف التلقائي
        temp_orders[order_id] = {
            "data": order_data,
            "timestamp": datetime.now()
        }
        
        print(f"[Flask] تم تخزين الطلب المؤقت بالمعرف: {order_id}")
        return jsonify({"order_id": order_id})

    @flask_app.route('/api/get_order/<order_id>')
    def get_temp_order(order_id):
        """يسترجع ويمسح الطلب المؤقت لنظام الكاشير."""
        # استخدام .pop() للاسترجاع والحذف في عملية واحدة
        order_info = temp_orders.pop(order_id, None)
        if order_info:
            print(f"[Flask] تم استرجاع وحذف الطلب المؤقت بالمعرف: {order_id}")
            return jsonify(order_info['data'])
        else:
            print(f"[Flask] لم يتم العثور على الطلب المؤقت بالمعرف: {order_id}")
            return jsonify({"error": "Order not found or already processed"}), 404
            
    @flask_app.route('/api/orders_status')
    def get_orders_status():
        """يرسل حالة الطلبات الحالية (قيد التجهيز والمكتملة) مع وقت التحضير المتوقع لكل طلب"""
        try:
            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # الحصول على الطلبات قيد التجهيز (الطلبات المدفوعة ولكن لم يتم تسليمها بعد)
            in_progress_orders = cursor.execute("""
                SELECT daily_order_number, order_date, payment_status, id 
                FROM orders 
                WHERE payment_status = 'Paid' AND DATE(order_date) = DATE('now', 'localtime')
                ORDER BY daily_order_number DESC
                LIMIT 50
            """).fetchall()
            
            # الحصول على الطلبات المكتملة (الطلبات التي تم تسليمها)
            completed_orders = cursor.execute("""
                SELECT daily_order_number, order_date, payment_status, id 
                FROM orders 
                WHERE payment_status = 'Completed' AND DATE(order_date) = DATE('now', 'localtime')
                ORDER BY daily_order_number DESC
                LIMIT 50
            """).fetchall()
            
            # تحويل البيانات إلى تنسيق مناسب للعرض
            in_progress_list = []
            for order in in_progress_orders:
                # حساب وقت التحضير المتوقع لكل طلب بناءً على المنتجات
                order_items = cursor.execute("""
                    SELECT oi.quantity, p.preparation_time, p.name, p.id as product_id
                    FROM order_items oi 
                    JOIN products p ON p.id = oi.product_id 
                    WHERE oi.order_id = ?
                """, (order['id'],)).fetchall()
                
                # حساب إجمالي وقت التحضير (أقصى وقت تحضير للمنتجات)
                max_prep_time = 0
                items_list = []
                for item in order_items:
                    if item['preparation_time'] > max_prep_time:
                        max_prep_time = item['preparation_time']
                    
                    items_list.append({
                        'name': item['name'],
                        'quantity': item['quantity'],
                        'product_id': item['product_id']
                    })
                
                # استخدام الوقت الافتراضي إذا لم يكن هناك وقت تحضير محدد
                if max_prep_time == 0:
                    config = load_config()
                    max_prep_time = config.get('preparation_time_minutes', 10)
                
                in_progress_list.append({
                    'orderNumber': order['daily_order_number'],
                    'time': datetime.strptime(order['order_date'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M'),
                    'preparationTime': max_prep_time,
                    'items': items_list
                })
            
            completed_list = []
            for order in completed_orders:
                # الحصول على معلومات المنتجات للطلبات المكتملة
                order_items = cursor.execute("""
                    SELECT oi.quantity, p.name, p.id as product_id
                    FROM order_items oi 
                    JOIN products p ON p.id = oi.product_id 
                    WHERE oi.order_id = ?
                """, (order['id'],)).fetchall()
                
                items_list = []
                for item in order_items:
                    items_list.append({
                        'name': item['name'],
                        'quantity': item['quantity'],
                        'product_id': item['product_id']
                    })
                
                completed_list.append({
                    'orderNumber': order['daily_order_number'],
                    'time': datetime.strptime(order['order_date'], '%Y-%m-%d %H:%M:%S').strftime('%H:%M'),
                    'items': items_list
                })
            
            conn.close()
            return jsonify({
                'inProgress': in_progress_list,
                'completed': completed_list
            })
        except Exception as e:
            print(f"[Flask Error] get_orders_status: {e}")
            return jsonify({"error": str(e)}), 500
            
    @flask_app.route('/api/complete_order/<int:order_number>', methods=['POST'])
    def complete_order(order_number):
        """تحديث حالة الطلب من 'Paid' إلى 'Completed' عند الانتهاء من تحضيره"""
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # التحقق من وجود الطلب
            order = cursor.execute("SELECT id FROM orders WHERE daily_order_number = ? AND payment_status = 'Paid'", (order_number,)).fetchone()
            
            if not order:
                conn.close()
                return jsonify({"error": "الطلب غير موجود أو ليس في حالة الدفع"}), 404
                
            # تحديث حالة الطلب إلى مكتمل
            cursor.execute("UPDATE orders SET payment_status = 'Completed' WHERE daily_order_number = ?", (order_number,))
            conn.commit()
            conn.close()
            
            return jsonify({"success": True, "message": f"تم تحديث حالة الطلب {order_number} إلى مكتمل"})
        except Exception as e:
            print(f"[Flask Error] complete_order: {e}")
            return jsonify({"error": str(e)}), 500
            
    @flask_app.route('/api/clear_completed_orders', methods=['POST'])
    def clear_completed_orders():
        """مسح جميع الطلبات المكتملة (تم التجهيز) لليوم الحالي"""
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # مسح الطلبات المكتملة لليوم الحالي فقط
            cursor.execute("""
                UPDATE orders 
                SET payment_status = 'Archived' 
                WHERE payment_status = 'Completed' 
                AND DATE(order_date) = DATE('now', 'localtime')
            """)
            
            # الحصول على عدد الصفوف المتأثرة
            affected_rows = cursor.rowcount
            conn.commit()
            conn.close()
            
            return jsonify({
                "success": True, 
                "message": f"تم مسح {affected_rows} من الطلبات المكتملة",
                "affected_rows": affected_rows
            })
        except Exception as e:
            print(f"[Flask Error] clear_completed_orders: {e}")
            return jsonify({"error": str(e)}), 500
            
    @flask_app.route('/api/clear_in_progress_orders', methods=['POST'])
    def clear_in_progress_orders():
        """مسح جميع الطلبات قيد التجهيز لليوم الحالي"""
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            # مسح الطلبات قيد التجهيز لليوم الحالي فقط
            cursor.execute("""
                UPDATE orders 
                SET payment_status = 'Archived' 
                WHERE payment_status = 'Paid' 
                AND DATE(order_date) = DATE('now', 'localtime')
            """)
            
            # الحصول على عدد الصفوف المتأثرة
            affected_rows = cursor.rowcount
            conn.commit()
            conn.close()
            
            return jsonify({
                "success": True, 
                "message": f"تم مسح {affected_rows} من الطلبات قيد التجهيز",
                "affected_rows": affected_rows
            })
        except Exception as e:
            print(f"[Flask Error] clear_in_progress_orders: {e}")
            return jsonify({"error": str(e)}), 500
            
    @flask_app.route('/api/user_role')
    def get_user_role():
        """تحديد نوع المستخدم (موظف أو عميل) بناءً على عنوان IP"""
        try:
            # الحصول على عنوان IP للمستخدم
            user_ip = request.remote_addr
            
            # التحقق مما إذا كان المستخدم على نفس الشبكة المحلية (موظف) أو من خارج الشبكة (عميل)
            # يمكن تعديل هذا المنطق حسب احتياجات المطعم
            
            # للتبسيط، نفترض أن المستخدمين على الشبكة المحلية هم موظفون
            # وأي مستخدم آخر هو عميل
            is_local_network = user_ip.startswith('192.168.') or user_ip.startswith('10.') or user_ip == '127.0.0.1' or user_ip == 'localhost'
            
            if is_local_network:
                role = 'employee'
            else:
                role = 'customer'
                
            return jsonify({
                "role": role,
                "ip": user_ip
            })
        except Exception as e:
            print(f"[Flask Error] get_user_role: {e}")
            # في حالة حدوث خطأ، نفترض أن المستخدم هو عميل لأسباب أمنية
            return jsonify({"role": "customer", "error": str(e)})

def run_flask_in_thread():
    """دالة لتشغيل خادم فلاسك في ثريد منفصل"""
    if not WEB_SERVER_SUPPORT:
        return
    try:
        flask_app.run(host='0.0.0.0', port=5000, debug=False)
    except Exception as e:
        print(f"Error starting Flask server: {e}")


# ==============================================================================
# --- تعريف أنماط المظهر (معدلة لتناسب شاشات اللمس) ---
# ==============================================================================

DARK_THEME_STYLESHEET = """
    QWidget {
        background-color: #2c3e50;
        color: #ecf0f1;
        border: 0px;
        font-family: Tahoma, Arial;
        font-size: 14px; 
    }
    QMainWindow, QDialog {
        background-color: #2c3e50;
    }
    QTabWidget::pane {
        border: 1px solid #34495e;
    }
    QTabBar::tab {
        background: #34495e;
        color: #ecf0f1;
        padding: 12px 18px; 
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        min-width: 120px;
        font-size: 15px;
    }
    QTabBar::tab:selected {
        background: #46627f;
        font-weight: bold;
    }
    QPushButton {
        background-color: #3498db;
        color: white;
        padding: 12px 18px; 
        border-radius: 5px;
        border: 1px solid #2980b9;
        font-weight: bold;
        font-size: 16px;
        min-height: 40px; 
    }
    QPushButton:hover {
        background-color: #4ea8e1;
    }
    QPushButton:pressed {
        background-color: #2980b9;
    }
    QPushButton:disabled {
        background-color: #5d6d7e;
        color: #bdc3c7;
    }
    QLineEdit, QDoubleSpinBox, QSpinBox, QTextEdit, QListWidget, QTableWidget, QComboBox {
        background-color: #34495e;
        color: #ecf0f1;
        border: 1px solid #566573;
        border-radius: 4px;
        padding: 8px;
        font-size: 15px;
    }
    QCheckBox {
        spacing: 10px;
        font-size: 18px;
        padding: 5px 0;
    }
    QCheckBox::indicator {
        width: 25px;
        height: 25px;
    }
    QHeaderView::section {
        background-color: #5d6d7e;
        color: white;
        padding: 6px;
        border: 1px solid #34495e;
        font-weight: bold;
        font-size: 15px;
    }
    QGroupBox {
        border: 1px solid #566573;
        border-radius: 5px;
        margin-top: 1ex;
        font-weight: bold;
        font-size: 16px;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top center;
        padding: 0 8px;
    }
    #NavPanel {
        background-color: #2c3e50;
        border-bottom: 1px solid #222; /* This will be ignored, but kept for reference */
    }
    QToolBar#NavToolBar QPushButton {
        padding: 5px 15px;
        margin: 2px;
        border-radius: 5px;
        border: none;
        font-size: 15px;
        background-color: #34495e; 
    }
    QToolBar#NavToolBar QPushButton:hover {
        background-color: #46627f;
    }
    QToolBar#NavToolBar QPushButton:checked {
        background-color: #3498db;
        font-weight: bold;
    }
    QFrame[Shape="StyledPanel"] {
        border: 1px solid #444;
        border-radius: 4px;
    }
    QMenu {
        background-color: #34495e;
        border: 1px solid #566573;
    }
    QMenu::item {
        padding: 10px 20px;
    }
    QMenu::item:selected {
        background-color: #3498db;
    }
"""

LIGHT_THEME_STYLESHEET = """
    QWidget {
        font-family: Tahoma, Arial;
        font-size: 14px;
    }
    QPushButton {
        padding: 10px 15px;
        font-size: 15px;
        min-height: 38px;
    }
    QGroupBox {
        font-weight: bold;
        font-size: 15px;
    }
    QCheckBox {
        spacing: 8px;
        font-size: 16px;
        padding: 5px 0;
    }
    QCheckBox::indicator {
        width: 20px;
        height: 20px;
    }
    #NavPanel {
        background-color: #ecf0f1;
        border-bottom: 1px solid #bdc3c7; /* This will be ignored, but kept for reference */
    }
    QToolBar#NavToolBar QPushButton {
        padding: 5px 15px;
        margin: 2px;
        border-radius: 5px;
        border: 1px solid #bdc3c7;
        font-size: 15px;
        background-color: #ffffff; 
    }
    QToolBar#NavToolBar QPushButton:hover {
        background-color: #f8f9f9;
    }
    QToolBar#NavToolBar QPushButton:checked {
        background-color: #3498db;
        color: white;
        border-color: #2980b9;
        font-weight: bold;
    }
"""

# ==============================================================================
# --- القسم الأول: الإعدادات العامة وقاعدة البيانات ---
# ==============================================================================

DB_NAME = 'food_truck_pos.db'
CONFIG_FILE = 'config.json'
CAMERA_CONFIG_FILE = 'camera_config.txt'

def create_database_and_tables():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, price REAL, category TEXT, is_available BOOLEAN DEFAULT 1, image_path TEXT, preparation_time INTEGER DEFAULT 0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS discount_codes (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, status TEXT, creation_date TEXT, usage_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS gift_vouchers (id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE, description TEXT, status TEXT, creation_date TEXT, usage_date TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, daily_order_number INTEGER, order_date TEXT, total_amount REAL, discount_code_id INTEGER, final_amount REAL, payment_method TEXT, gift_voucher_code TEXT, payment_status TEXT NOT NULL DEFAULT "Paid")')
    cursor.execute('CREATE TABLE IF NOT EXISTS order_items (id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER, price_per_item REAL, FOREIGN KEY (order_id) REFERENCES orders (id) ON DELETE CASCADE, FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS modifiers (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, price_change REAL DEFAULT 0.0)')
    cursor.execute('CREATE TABLE IF NOT EXISTS product_modifier_links (product_id INTEGER, modifier_id INTEGER, PRIMARY KEY (product_id, modifier_id), FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE, FOREIGN KEY (modifier_id) REFERENCES modifiers (id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS order_item_modifiers (id INTEGER PRIMARY KEY, order_item_id INTEGER, modifier_id INTEGER, FOREIGN KEY (order_item_id) REFERENCES order_items (id) ON DELETE CASCADE, FOREIGN KEY (modifier_id) REFERENCES modifiers (id) ON DELETE CASCADE)')
    cursor.execute('CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS expenses (id INTEGER PRIMARY KEY, description TEXT NOT NULL, amount REAL NOT NULL, category TEXT, expense_date TEXT, receipt_image_path TEXT)')
    
    try: cursor.execute('SELECT daily_order_number FROM orders LIMIT 1')
    except sqlite3.OperationalError: cursor.execute('ALTER TABLE orders ADD COLUMN daily_order_number INTEGER')
    try: cursor.execute('SELECT payment_status FROM orders LIMIT 1')
    except sqlite3.OperationalError: cursor.execute('ALTER TABLE orders ADD COLUMN payment_status TEXT NOT NULL DEFAULT "Paid"')
    try: cursor.execute('SELECT preparation_time FROM products LIMIT 1')
    except sqlite3.OperationalError: cursor.execute('ALTER TABLE products ADD COLUMN preparation_time INTEGER DEFAULT 0')
    
    cursor.execute("INSERT OR IGNORE INTO app_settings (key, value) VALUES ('daily_order_counter', '0')")

    conn.commit(); conn.close()

def add_sample_data_if_needed():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    if not os.path.exists('web/static/default.png'):
        if not os.path.exists('web/static'):
            os.makedirs('web/static')
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (200, 200), color = (128, 128, 128))
            d = ImageDraw.Draw(img)
            d.text((50,90), "No Image", fill=(255,255,255))
            img.save('web/static/default.png')
        except ImportError:
            pass 

    if cursor.execute("SELECT COUNT(*) FROM products").fetchone()[0] == 0:
        p_data = [ (1, 'برجر لحم', 25.0, 'برجر', 1, ''), (2, 'اسكلوب دجاج', 22.0, 'اسكلوب', 1, ''), (3, 'بطاطس مقلية', 10.0, 'مقبلات', 1, ''), (4, 'مشروب غازي', 5.0, 'مشروبات', 1, '')]
        cursor.executemany("INSERT OR IGNORE INTO products (id, name, price, category, is_available, image_path) VALUES (?, ?, ?, ?, ?, ?)", p_data)
        m_data = [(1, 'بدون بصل', 0.0), (2, 'بدون مخلل', 0.0), (3, 'جبنة إضافية', 3.0), (4, 'كاتشب إضافي', 1.0)]
        cursor.executemany("INSERT OR IGNORE INTO modifiers (id, name, price_change) VALUES (?, ?, ?)", m_data)
        l_data = [(1, 1), (1, 2), (1, 3), (2, 1), (2, 2), (2, 3), (3, 4)]
        cursor.executemany("INSERT OR IGNORE INTO product_modifier_links (product_id, modifier_id) VALUES (?, ?)", l_data)
        conn.commit()
    conn.close()

# ==============================================================================
# --- القسم الثاني: الدوال المساعدة (طباعة، خطوط، باركود، إعدادات) ---
# ==============================================================================
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('10.255.255.255', 1))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def generate_qr_for_order(order_id, order_date_str, daily_order_number):
    original_value = f"INVOICE-{order_date_str}-{daily_order_number}"
    qr_value_bytes = base64.b64encode(original_value.encode('utf-8'))
    qr_value = qr_value_bytes.decode('utf-8')
    qr_path = f"invoice_qr_{order_id}.png"
    try:
        qrcode.make(qr_value).save(qr_path)
    except Exception as e:
        print(f"فشل إنشاء رمز QR للفاتورة: {e}")
        return None
    return qr_path

def get_next_order_number(cursor):
    res = cursor.execute("SELECT value FROM app_settings WHERE key = 'daily_order_counter'").fetchone()
    current_counter = int(res[0]) if res else 0
    next_number = current_counter + 1
    cursor.execute("UPDATE app_settings SET value = ? WHERE key = 'daily_order_counter'", (str(next_number),))
    return next_number

def peek_next_order_number():
    with sqlite3.connect(DB_NAME) as conn:
        res = conn.execute("SELECT value FROM app_settings WHERE key = 'daily_order_counter'").fetchone()
        return (int(res[0]) if res else 0) + 1

def reset_daily_counter():
    reply = QMessageBox.question(None, "تأكيد إعادة التعيين", "هل أنت متأكد من رغبتك في إعادة بدء عداد الطلبات من رقم 1؟\n\nيجب القيام بهذه العملية في بداية كل يوم عمل.", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if reply == QMessageBox.Yes:
        try:
            conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
            cursor.execute("UPDATE app_settings SET value = '0' WHERE key = 'daily_order_counter'")
            conn.commit(); conn.close(); next_num = peek_next_order_number()
            QMessageBox.information(None, "تم", f"تم إعادة تعيين العداد بنجاح.\nالطلب القادم سيحمل الرقم: {next_num}")
        except Exception as e: QMessageBox.critical(None, "خطأ", f"فشل إعادة تعيين العداد: {e}")

def register_arabic_font():
    font_path = ""
    if sys.platform == "win32":
        fonts_dir = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts")
        for font in ['tahoma.ttf', 'arial.ttf']:
            if os.path.exists(os.path.join(fonts_dir, font)): font_path = os.path.join(fonts_dir, font); break
    if font_path and ARABIC_SUPPORT:
        try: pdfmetrics.registerFont(TTFont('Arabic-Font', font_path)); return 'Arabic-Font'
        except: return 'Helvetica'
    return 'Helvetica'

ARABIC_FONT_NAME = register_arabic_font()

def load_config():
    defaults = {
        'restaurant_name': 'مطعمي المتنقل', 'thank_you_message': 'شكراً لزيارتكم!', 'logo_path': '', 
        'issue_gifts_enabled': True, 'issue_discounts_enabled': True, 
        'default_gift_description': 'مشروب مجاني', 'gift_chance_percentage': 25, 
        'currency_symbol': 'ريال', 'discount_percentage': 20,
        'customer_display_timeout_minutes': 30, 'customer_display_promo_message': 'أهلاً بكم!',
        'cds_media_path': '',
        'cds_font_size': 38,
        'theme': 'light',
        'pos_product_columns': 3,
        'pos_bill_ratio': 40,
        'preparation_time_minutes': 10
    }
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f: config = json.load(f); defaults.update(config); return defaults
    except (FileNotFoundError, json.JSONDecodeError): return defaults

def do_print(file_path):
    """دالة الطباعة المحسنة باستخدام win32print لـ Windows"""
    try:
        if sys.platform == "win32" and WINDOWS_PRINT_SUPPORT:
            # الحصول على الطابعة المحددة من الإعدادات
            config = load_config()
            selected_printer = config.get('selected_printer', 'الطابعة الافتراضية')
            
            # إذا كانت الطابعة المحددة هي الافتراضية، استخدم الطابعة الافتراضية
            if selected_printer == 'الطابعة الافتراضية':
                printer_name = win32print.GetDefaultPrinter()
            else:
                printer_name = selected_printer
            
            if not printer_name:
                raise Exception("لم يتم العثور على طابعة افتراضية")
            
            # طباعة الملف مباشرة
            win32api.ShellExecute(0, "print", file_path, None, ".", 0)
            
        elif sys.platform == "win32":
            # الطريقة القديمة كبديل
            os.startfile(file_path, "print")
        else:
            # للأنظمة الأخرى
            subprocess.run(["lpr", file_path] if sys.platform == "darwin" else ["lp", file_path], check=True)
            
    except Exception as e:
        error_msg = f"فشل الطباعة التلقائية.\nيمكنك طباعة '{os.path.basename(file_path)}' يدويًا.\n\nالتفاصيل: {e}"
        QMessageBox.warning(None, "خطأ طباعة", error_msg)

def get_available_printers():
    """الحصول على قائمة الطابعات المتاحة"""
    if sys.platform == "win32" and WINDOWS_PRINT_SUPPORT:
        try:
            printers = []
            for printer in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS):
                printers.append(printer[2])  # اسم الطابعة
            return printers
        except Exception:
            return []
    return []

def print_with_specific_printer(file_path, printer_name=None):
    """طباعة الملف على طابعة محددة"""
    try:
        if sys.platform == "win32" and WINDOWS_PRINT_SUPPORT:
            if not printer_name:
                printer_name = win32print.GetDefaultPrinter()
            
            # التحقق من وجود الطابعة
            available_printers = get_available_printers()
            if printer_name not in available_printers:
                raise Exception(f"الطابعة '{printer_name}' غير متاحة")
            
            # طباعة الملف
            win32api.ShellExecute(0, "print", file_path, None, ".", 0)
            return True
            
        else:
            # استخدام الطريقة العادية
            return do_print(file_path)
            
    except Exception as e:
        error_msg = f"فشل الطباعة على الطابعة المحددة.\nالتفاصيل: {e}"
        QMessageBox.warning(None, "خطأ طباعة", error_msg)
        return False

class PrinterSelectionDialog(QDialog):
    """نافذة اختيار الطابعة"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("اختيار الطابعة")
        self.setModal(True)
        self.selected_printer = None
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # عنوان
        title_label = QLabel("اختر الطابعة المفضلة:")
        title_label.setStyleSheet("font-size: 14px; font-weight: bold; margin: 10px;")
        layout.addWidget(title_label)
        
        # قائمة الطابعات
        self.printer_combo = QComboBox()
        printers = get_available_printers()
        if printers:
            self.printer_combo.addItems(printers)
            # تحديد الطابعة الافتراضية
            default_printer = win32print.GetDefaultPrinter() if WINDOWS_PRINT_SUPPORT else ""
            if default_printer in printers:
                index = printers.index(default_printer)
                self.printer_combo.setCurrentIndex(index)
        else:
            self.printer_combo.addItem("لا توجد طابعات متاحة")
            self.printer_combo.setEnabled(False)
        
        layout.addWidget(self.printer_combo)
        
        # معلومات الطابعة
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: #666; font-size: 12px; margin: 5px;")
        layout.addWidget(self.info_label)
        
        # أزرار
        button_layout = QHBoxLayout()
        test_button = QPushButton("اختبار الطباعة")
        test_button.clicked.connect(self.test_print)
        button_layout.addWidget(test_button)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_layout.addWidget(button_box)
        
        layout.addLayout(button_layout)
        self.setLayout(layout)
        
        # تحديث المعلومات عند تغيير الطابعة
        self.printer_combo.currentTextChanged.connect(self.update_printer_info)
        self.update_printer_info()
        
    def update_printer_info(self):
        """تحديث معلومات الطابعة المحددة"""
        if WINDOWS_PRINT_SUPPORT and self.printer_combo.currentText() != "لا توجد طابعات متاحة":
            try:
                printer_name = self.printer_combo.currentText()
                printer_info = win32print.GetPrinter(win32print.OpenPrinter(printer_name)[0], 2)
                status = printer_info['Status']
                
                status_text = "متصل" if status == 0 else "غير متصل"
                info_text = f"الحالة: {status_text}\nالطابعة: {printer_name}"
                self.info_label.setText(info_text)
            except Exception:
                self.info_label.setText("لا يمكن الحصول على معلومات الطابعة")
        else:
            self.info_label.setText("")
    
    def test_print(self):
        """اختبار الطباعة"""
        if not WINDOWS_PRINT_SUPPORT:
            QMessageBox.warning(self, "خطأ", "دعم الطباعة غير متاح على هذا النظام")
            return
            
        printer_name = self.printer_combo.currentText()
        if printer_name == "لا توجد طابعات متاحة":
            QMessageBox.warning(self, "خطأ", "لا توجد طابعات متاحة للاختبار")
            return
            
        try:
            # إنشاء ملف اختبار بسيط
            test_file = "test_print.pdf"
            c = canvas.Canvas(test_file, pagesize=(80 * mm, 50 * mm))
            c.setFont("Helvetica", 12)
            c.drawString(10 * mm, 40 * mm, "اختبار الطباعة")
            c.drawString(10 * mm, 30 * mm, f"الطابعة: {printer_name}")
            c.drawString(10 * mm, 20 * mm, f"التاريخ: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            c.save()
            
            # طباعة ملف الاختبار
            if print_with_specific_printer(test_file, printer_name):
                QMessageBox.information(self, "نجح الاختبار", "تم إرسال صفحة الاختبار للطباعة بنجاح")
            else:
                QMessageBox.warning(self, "فشل الاختبار", "فشل في إرسال صفحة الاختبار للطباعة")
                
            # حذف ملف الاختبار
            if os.path.exists(test_file):
                os.remove(test_file)
                
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"حدث خطأ أثناء اختبار الطباعة:\n{e}")
    
    def get_selected_printer(self):
        """الحصول على الطابعة المحددة"""
        if self.printer_combo.currentText() != "لا توجد طابعات متاحة":
            return self.printer_combo.currentText()
        return None

def print_receipt_full(order_details, issues_to_print, file_path):
    config = load_config(); currency = config['currency_symbol']; est_height = 8.0
    if config.get('logo_path') and os.path.exists(config['logo_path']): est_height += 25
    est_height += 25;
    for item in order_details['items']:
        est_height += 8
        if item.get('modifiers'): est_height += (len(item['modifiers']) * 6)
    est_height += 10;
    if order_details['discount'] > 0: est_height += 8
    if order_details.get('gift_description'): est_height += 8
    if order_details.get('payment_status') != 'Paid': est_height += 15
    est_height += 18
    if issues_to_print: est_height += 5 + (len(issues_to_print) * 42)
    est_height += 12; est_height += 25
    page_height_mm = max(est_height, 80)
    try:
        c = canvas.Canvas(file_path, pagesize=(80 * mm, page_height_mm * mm))
        def draw_arabic_right(x, y, text, font=ARABIC_FONT_NAME, size=10):
            c.setFont(font, size); text_to_draw = str(text)
            if ARABIC_SUPPORT: text_to_draw = get_display(arabic_reshaper.reshape(text_to_draw))
            c.drawRightString(x * mm, y * mm, text_to_draw)
        y = page_height_mm - 8
        if config.get('logo_path') and os.path.exists(config['logo_path']):
            try: c.drawImage(config['logo_path'], 30 * mm, (y - 18) * mm, width=20*mm, height=20*mm, preserveAspectRatio=True, mask='auto'); y -= 22
            except Exception as e: print(f"Error loading top logo: {e}")

        reshaped_name = get_display(arabic_reshaper.reshape(config['restaurant_name'])) if ARABIC_SUPPORT else config['restaurant_name']
        c.setFont(ARABIC_FONT_NAME, 16); c.drawCentredString(40*mm, y*mm, reshaped_name); y -= 8
        c.setFont("Helvetica-Bold", 20); c.drawCentredString(40*mm, y*mm, f"Order #{order_details['daily_order_number']}"); y -= 8
        c.setFont('Helvetica', 8); c.drawCentredString(40*mm, y*mm, order_details['date']); y -= 5
        c.line(5 * mm, y * mm, 75 * mm, y * mm); y -= 6; c.setFont(ARABIC_FONT_NAME, 10)
        for item in order_details['items']:
            draw_arabic_right(75, y, f"{item['quantity']}x {item['name']}"); c.drawString(10 * mm, y * mm, f"{item['item_total_price']:.2f}"); y -= 7
            c.setFont(ARABIC_FONT_NAME, 8)
            for mod in item.get('modifiers', []): draw_arabic_right(70, y, f"  - {mod['name']}" + (f" (+{mod['price_change']:.2f})" if mod['price_change'] > 0 else "")); y -= 5.5
            c.setFont(ARABIC_FONT_NAME, 10)
        y -= 3; c.line(5 * mm, y * mm, 75 * mm, y * mm); y -= 8
        draw_arabic_right(75, y, "المجموع الفرعي:"); c.drawString(10 * mm, y * mm, f"{order_details['subtotal']:.2f}"); y -= 8
        if order_details['discount'] > 0: draw_arabic_right(75, y, "الخصم:"); c.drawString(10 * mm, y * mm, f"({order_details['discount']:.2f})"); y -= 8
        if order_details.get('gift_description'): draw_arabic_right(75, y, f"هدية: {order_details['gift_description']}"); y -= 8
        
        if order_details.get('payment_status') != 'Paid':
            c.saveState()
            c.setFont('Helvetica-Bold', 18)
            c.setFillColorRGB(0.8, 0.1, 0.1) # Dark red color
            unpaid_text_reshaped = get_display(arabic_reshaper.reshape("فاتورة غير مدفوعة"))
            c.drawCentredString(40 * mm, (y - 5) * mm, unpaid_text_reshaped)
            c.restoreState()
            y -= 15

        y -= 2; draw_arabic_right(75, y, "الإجمالي:", size=12); c.setFont('Helvetica-Bold', 12); c.drawString(10 * mm, y * mm, f"{order_details['total']:.2f} {currency}"); y -= 7
        draw_arabic_right(75, y, f"(الدفع: {order_details['payment_method']})", size=8); y -= 8
        if issues_to_print:
            c.line(5 * mm, y * mm, 75 * mm, y * mm); y -= 2
            for issue_details in issues_to_print:
                y -= 38; c.roundRect(8 * mm, y * mm, 64 * mm, 34 * mm, 4)
                if issue_details.get('qr_path') and os.path.exists(issue_details['qr_path']): c.drawImage(issue_details['qr_path'], 10 * mm, y * mm + 3*mm, width=28 * mm, height=28 * mm)
                title = f"كوبون خصم {config['discount_percentage']}%" if issue_details['type'] == 'discount' else "قسيمة هدية!"
                description = "استخدمه في طلبك القادم" if issue_details['type'] == 'discount' else issue_details['description']
                draw_arabic_right(70, y + 24, title, size=11); draw_arabic_right(70, y + 17, description, size=9)
                c.setFont("Helvetica-Bold", 10); c.drawRightString(70 * mm, y * mm + 8*mm, issue_details['code']); y -= 4
        y -= 8;
        reshaped_thanks = get_display(arabic_reshaper.reshape(config['thank_you_message'])) if ARABIC_SUPPORT else config['thank_you_message']
        c.setFont(ARABIC_FONT_NAME, 10); c.drawCentredString(40*mm, y*mm, reshaped_thanks); y -= 22

        order_date_only = datetime.strptime(order_details['date'], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d")
        qr_code_path = generate_qr_for_order(order_details['id'], order_date_only, order_details['daily_order_number'])
        if qr_code_path and os.path.exists(qr_code_path):
            try: c.drawImage(qr_code_path, 30 * mm, y * mm, width=20 * mm, height=20 * mm)
            except Exception as e: print(f"Error drawing QR code: {e}")

        c.save()
    except Exception as e: QMessageBox.critical(None, "خطأ PDF", f"فشل إنشاء إيصال الزبون: {e}"); return
    do_print(file_path)

def print_kitchen_ticket_enhanced(order_details, file_path):
    header_space = 40.0; item_space = sum(15 + (len(item.get('modifiers', [])) * 7) for item in order_details['items']); footer_space = 20.0
    total_height = max(header_space + item_space + footer_space, 120.0)
    try:
        c = canvas.Canvas(file_path, pagesize=(80 * mm, total_height * mm)); y = total_height - 10
        # تأكد من أن حالة الدفع صحيحة عند اختيار طريقة الدفع
        if order_details.get('payment_method') and order_details.get('payment_method') != "غير محدد":
            order_details['payment_status'] = 'Paid'
            
        if order_details.get('payment_status') != 'Paid':
            c.setFillColorRGB(1.0, 0.8, 0.8) 
        else:
            c.setFillColorRGB(0.9, 0.9, 0.9)
        c.rect(15 * mm, (y-15) * mm, 50 * mm, 12 * mm, fill=1, stroke=1)

        c.setFillColorRGB(0, 0, 0); c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(40 * mm, (y-10) * mm, f"ORDER #{order_details['daily_order_number']}")
        y -= 18
        payment_method_reshaped = get_display(arabic_reshaper.reshape(order_details['payment_method'])) if ARABIC_SUPPORT else order_details['payment_method']
        c.setFont(ARABIC_FONT_NAME, 8); date_time = order_details['date'].split(' '); c.drawCentredString(40 * mm, y * mm, f"{date_time[1]} | {payment_method_reshaped}"); y -= 10
        c.setLineWidth(2); c.line(5 * mm, y * mm, 75 * mm, y * mm); y -= 2; c.setLineWidth(0.5); c.line(5 * mm, y * mm, 75 * mm, y * mm); y -= 12
        for i, item in enumerate(order_details['items']):
            box_height = 14 + (len(item.get('modifiers', [])) * 6)
            if i % 2 == 0: c.setFillColorRGB(0.95, 0.95, 0.95); c.rect(8 * mm, (y - box_height + 2) * mm, 64 * mm, box_height * mm, fill=1, stroke=0); c.setFillColorRGB(0, 0, 0)
            c.circle(12 * mm, (y-4) * mm, 3 * mm, stroke=1, fill=0); c.setFont("Helvetica-Bold", 10); c.drawCentredString(12 * mm, (y-6) * mm, str(item['quantity']))
            display_name = get_display(arabic_reshaper.reshape(item['name'])) if ARABIC_SUPPORT else item['name']; c.setFont(ARABIC_FONT_NAME, 12); c.drawRightString(70 * mm, (y-6) * mm, display_name); y -= 12
            for mod in item.get('modifiers', []):
                mod_symbol = "+" if mod.get('price_change', 0) > 0 else "-"; mod_display_text = f"{mod_symbol} {mod['name']}"
                mod_display = get_display(arabic_reshaper.reshape(mod_display_text)) if ARABIC_SUPPORT else mod_display_text
                c.setFont(ARABIC_FONT_NAME, 9); c.drawRightString(65 * mm, y * mm, mod_display); y -= 6
            y -= 4
        y -= 5; c.setLineWidth(1); c.line(10 * mm, y * mm, 70 * mm, y * mm)
        if order_details.get('gift_description'):
            y -= 8; c.setFont(ARABIC_FONT_NAME, 10); gift_text_simple = f"هدية: {order_details['gift_description']}"
            gift_text = get_display(arabic_reshaper.reshape(gift_text_simple)) if ARABIC_SUPPORT else gift_text_simple
            c.drawCentredString(40 * mm, y * mm, gift_text)
        c.save(); print(f"تم إنشاء تذكرة المطبخ المحسّنة: {file_path}")
    except Exception as e: print(f"خطأ في تذكرة المطبخ المحسّنة: {e}"); return
    do_print(file_path)

# ==============================================================================
# --- القسم الثالث: النوافذ المنبثقة والكاميرا ---
# ==============================================================================

class WifiQRGeneratorDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("إنشاء رمز QR للمنيو الرقمي")
        self.setMinimumWidth(500)
        
        layout = QVBoxLayout(self)
        
        info_label = QLabel(
            "هذه النافذة ستنشئ رمز QR ليقوم العملاء بمسحه.\n"
            "عند المسح، سيتصل هاتف العميل بالواي فاي الخاص بك، وسيظهر له إشعار لفتح المنيو الرقمي."
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)

        form_layout = QFormLayout()
        self.ip_address = QLineEdit(get_local_ip())
        self.ip_address.setReadOnly(True)
        self.ssid = QLineEdit()
        self.password = QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        
        form_layout.addRow("عنوان IP لخادم المنيو (تلقائي):", self.ip_address)
        form_layout.addRow("اسم شبكة الواي فاي (SSID):", self.ssid)
        form_layout.addRow("كلمة مرور الواي فاي:", self.password)
        
        layout.addLayout(form_layout)
        
        generate_btn = QPushButton("إنشاء رمز QR")
        generate_btn.clicked.connect(self.generate_qr)
        layout.addWidget(generate_btn)
        
        self.qr_label = QLabel("امسح الرمز لاختباره. احفظه وقم بطباعته للعملاء.")
        self.qr_label.setAlignment(Qt.AlignCenter)
        self.qr_label.setMinimumSize(300, 300)
        self.qr_label.setStyleSheet("border: 1px dashed grey; padding: 10px;")
        layout.addWidget(self.qr_label)

    def generate_qr(self):
        ssid = self.ssid.text().strip()
        password = self.password.text().strip()

        if not ssid:
            QMessageBox.warning(self, "خطأ", "الرجاء إدخال اسم شبكة الواي فاي.")
            return

        wifi_string = f"WIFI:T:WPA;S:{ssid};P:{password};;"
        qr_img = qrcode.make(wifi_string)
        
        img_byte_array = QByteArray()
        buffer = QBuffer(img_byte_array)
        buffer.open(QIODevice.WriteOnly)
        qr_img.save(buffer, "PNG")
        
        pixmap = QPixmap()
        pixmap.loadFromData(img_byte_array)
        
        self.qr_label.setPixmap(pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation))

class CameraThread(QThread):
    code_found = pyqtSignal(str)
    error_found = pyqtSignal(str)

    def __init__(self, index, continuous=False, parent=None):
        super().__init__(parent)
        self.idx = index
        self.continuous = continuous
        self.running = True

    def run(self):
        cap = cv2.VideoCapture(self.idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            self.error_found.emit(f"فشل فتح الكاميرا {self.idx}")
            return

        use_pyzbar = PYZBAR_SUPPORT
        if not use_pyzbar:
            detector = cv2.QRCodeDetector()

        while self.running:
            ret, frame = cap.read()
            if ret:
                data = None
                if use_pyzbar:
                    barcodes = pyzbar.decode(frame)
                    if barcodes:
                        data = barcodes[0].data.decode('utf-8')
                else:
                    detected_data, _, _ = detector.detectAndDecode(frame)
                    if detected_data:
                        data = detected_data

                if data:
                    self.code_found.emit(data)
                    if not self.continuous:
                        self.stop()

            if self.continuous:
                self.msleep(100)

        cap.release()

    def stop(self):
        self.running = False
        self.quit()
        self.wait()


class CameraSettingsDialog(QDialog):
    saved = pyqtSignal(int)
    def __init__(self, current_idx, parent=None):
        super().__init__(parent); self.setWindowTitle("إعدادات الكاميرا"); layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"الكاميرا الحالية: {current_idx}")); search_btn = QPushButton("🔍 بحث")
        search_btn.clicked.connect(self.search); self.combo = QComboBox(); save_btn = QPushButton("💾 حفظ")
        save_btn.clicked.connect(self.save); self.status = QLabel(""); layout.addWidget(search_btn)
        layout.addWidget(self.combo); layout.addWidget(save_btn); layout.addWidget(self.status)
    def search(self):
        self.status.setText("⏳ جاري البحث..."); QApplication.processEvents()
        cams = [i for i in range(5) if cv2.VideoCapture(i, cv2.CAP_DSHOW).isOpened()]; self.combo.clear()
        if cams: self.combo.addItems(map(str, cams)); self.status.setText(f"✅ تم العثور على {len(cams)} كاميرا.")
        else: self.status.setText("❌ لم يتم العثور على كاميرات!")
    def save(self):
        if self.combo.currentText(): self.saved.emit(int(self.combo.currentText())); self.accept()

class AddToCartDialog(QDialog):
    def __init__(self, product_id, product_name, existing_item=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"إضافة وتخصيص: {product_name}")
        self.setMinimumWidth(450)
        layout = QVBoxLayout(self)

        self.current_quantity = 1
        qty_group = QGroupBox("الكمية")
        qty_layout = QHBoxLayout(qty_group)
        qty_layout.setContentsMargins(10, 20, 10, 10)

        self.minus_btn = QPushButton("-")
        self.minus_btn.setFixedSize(70, 70)
        self.minus_btn.setStyleSheet("font-size: 28px; font-weight: bold;")

        self.quantity_label = QLabel(str(self.current_quantity))
        self.quantity_label.setAlignment(Qt.AlignCenter)
        self.quantity_label.setMinimumWidth(100)
        self.quantity_label.setStyleSheet("font-size: 28px; font-weight: bold; border: 1px solid #566573; border-radius: 5px; background-color: #34495e; qproperty-alignment: 'AlignCenter';")

        self.plus_btn = QPushButton("+")
        self.plus_btn.setFixedSize(70, 70)
        self.plus_btn.setStyleSheet("font-size: 28px; font-weight: bold;")

        qty_layout.addWidget(self.minus_btn)
        qty_layout.addStretch()
        qty_layout.addWidget(self.quantity_label)
        qty_layout.addStretch()
        qty_layout.addWidget(self.plus_btn)

        layout.addWidget(qty_group)
        self.plus_btn.clicked.connect(self.increase_quantity)
        self.minus_btn.clicked.connect(self.decrease_quantity)

        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)

        mods_group = QGroupBox("الإضافات المتاحة")
        mods_layout = QVBoxLayout(mods_group)
        self.checkboxes, self.mods_data = [], []
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("SELECT m.id, m.name, m.price_change FROM modifiers m JOIN product_modifier_links l ON m.id = l.modifier_id WHERE l.product_id = ?", (product_id,))
            self.mods_data = cursor.fetchall()
            conn.close()
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تحميل الإضافات: {e}")

        if not self.mods_data:
            mods_layout.addWidget(QLabel("<i>لا توجد إضافات متاحة.</i>"))
        else:
            for _, name, price in self.mods_data:
                cb = QCheckBox(f"{name} (+{price:.2f} {load_config()['currency_symbol']})")
                self.checkboxes.append(cb)
                mods_layout.addWidget(cb)
        
        layout.addWidget(mods_group)

        if existing_item:
            self.current_quantity = existing_item['qty']
            self.quantity_label.setText(str(self.current_quantity))
            existing_mod_ids = {m['id'] for m in existing_item['mods']}
            for i, mod_data in enumerate(self.mods_data):
                if mod_data[0] in existing_mod_ids:
                    self.checkboxes[i].setChecked(True)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def increase_quantity(self):
        if self.current_quantity < 99:
            self.current_quantity += 1
            self.quantity_label.setText(str(self.current_quantity))

    def decrease_quantity(self):
        if self.current_quantity > 1:
            self.current_quantity -= 1
            self.quantity_label.setText(str(self.current_quantity))

    def get_selection(self):
        selected_mods_data = []
        for i, cb in enumerate(self.checkboxes):
            if cb.isChecked():
                # self.mods_data contains (id, name, price_change)
                mod_tuple = self.mods_data[i]
                selected_mods_data.append({'id': mod_tuple[0], 'name': mod_tuple[1], 'price_change': mod_tuple[2]})
        
        return {'quantity': self.current_quantity, 'modifiers': selected_mods_data}


class CheckoutDialog(QDialog):
    def __init__(self, total, parent=None):
        super().__init__(parent); self.setWindowTitle("إنهاء الطلب والدفع"); layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"<h2>المبلغ الإجمالي: {total:.2f} {load_config()['currency_symbol']}</h2>"))
        layout.addWidget(QLabel("اختر طريقة الدفع أو إصدار الفاتورة:"))
        
        # إضافة مجموعة للأزرار لتوضيح الخيارات
        payment_group = QGroupBox("طرق الدفع")
        payment_layout = QVBoxLayout()
        
        self.cash = QRadioButton("💵 كاش (مدفوع الآن)")
        self.card = QRadioButton("💳 بطاقة (مدفوع الآن)")
        self.pay_later = QRadioButton("🧾 دفع لاحقاً (إصدار فاتورة غير مدفوعة)")

        self.cash.setChecked(True)
        payment_layout.addWidget(self.cash)
        payment_layout.addWidget(self.card)
        payment_layout.addWidget(self.pay_later)
        payment_group.setLayout(payment_layout)
        layout.addWidget(payment_group)
        
        # إضافة توضيح لحالة الدفع
        status_label = QLabel("<b>ملاحظة:</b> سيتم عرض حالة الدفع في شاشة المطبخ")
        layout.addWidget(status_label)
        
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)

    def get_selection(self):
        if self.cash.isChecked(): return "Cash", "Paid", "كاش"
        if self.card.isChecked(): return "Card", "Paid", "بطاقة"
        if self.pay_later.isChecked(): return "PayLater", "Unpaid", "دفع لاحقاً"
        return None, None, None

class ParkedOrdersDialog(QDialog):
    def __init__(self, parked_orders, parent=None):
        super().__init__(parent); self.setWindowTitle("استئناف طلب مُعلَّق"); self.selected_order_id = None
        layout = QVBoxLayout(self); layout.addWidget(QLabel("اختر الطلب الذي تريد استئنافه:"))
        self.list_widget = QListWidget()
        for order in parked_orders:
            item_count = sum(item['qty'] for item in order['order_data'])
            display_text = f"طلب معلَّق في: {order['id']} ({item_count} أصناف)"
            list_item = QListWidgetItem(display_text); list_item.setData(Qt.UserRole, order['id']); self.list_widget.addItem(list_item)
        self.list_widget.itemDoubleClicked.connect(self.accept); layout.addWidget(self.list_widget)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); btns.accepted.connect(self.accept); btns.rejected.connect(self.reject); layout.addWidget(btns)
    def accept(self):
        if not self.list_widget.currentItem(): QMessageBox.warning(self, "تنبيه", "الرجاء اختيار طلب أولاً."); return
        self.selected_order_id = self.list_widget.currentItem().data(Qt.UserRole); super().accept()

class ScreenSelectionDialog(QDialog):
    def __init__(self, screens, parent=None):
        super().__init__(parent)
        self.setWindowTitle("اختر شاشة العرض")
        self.selected_screen_index = -1
        
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("تم العثور على عدة شاشات. الرجاء اختيار الشاشة لعرض نافذة العملاء عليها:"))
        
        self.list_widget = QListWidget()
        for i, screen in enumerate(screens):
            size = screen.size()
            item = QListWidgetItem(f"الشاشة {i + 1} ({size.width()}x{size.height()})")
            item.setData(Qt.UserRole, i)
            self.list_widget.addItem(item)
        
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        if self.list_widget.currentItem():
            self.selected_screen_index = self.list_widget.currentItem().data(Qt.UserRole)
            super().accept()
        else:
            QMessageBox.warning(self, "تنبيه", "الرجاء اختيار شاشة أولاً.")

class EditInvoiceDialog(QDialog):
    def __init__(self, order_id, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"تعديل الفاتورة (معرف: #{order_id})")
        self.setMinimumSize(800, 600)
        self.order_id = order_id
        self.is_paid = True
        self.final_amount = 0.0

        self.layout = QVBoxLayout(self)

        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.StyledPanel)
        info_layout = QGridLayout(info_frame)
        self.order_info = QLabel(f"جاري تحميل الفاتورة (معرف: #{order_id})...")
        self.payment_status_label = QLabel()
        info_layout.addWidget(self.order_info, 0, 0)
        info_layout.addWidget(self.payment_status_label, 0, 1, Qt.AlignRight)
        self.layout.addWidget(info_frame)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["المعرف", "المنتج", "الكمية", "السعر", "الإجمالي"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectRows); self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.layout.addWidget(self.table)

        actions_layout = QHBoxLayout()
        self.remove_btn = QPushButton("🗑️ حذف المحدد")
        self.remove_btn.clicked.connect(self.remove_item)
        self.edit_qty_btn = QPushButton("✏️ تعديل الكمية")
        self.edit_qty_btn.clicked.connect(self.edit_quantity)
        actions_layout.addWidget(self.remove_btn)
        actions_layout.addWidget(self.edit_qty_btn)
        self.layout.addLayout(actions_layout)

        totals_layout = QFormLayout()
        self.subtotal_lbl = QLabel("0.00")
        self.discount_input = QDoubleSpinBox()
        self.discount_input.setRange(0, 10000)
        self.discount_input.setSingleStep(1.0)
        self.discount_input.valueChanged.connect(self.update_totals)
        self.final_lbl = QLabel("0.00")
        totals_layout.addRow("المجموع الفرعي:", self.subtotal_lbl)
        totals_layout.addRow("الخصم:", self.discount_input)
        totals_layout.addRow("الإجمالي النهائي:", self.final_lbl)
        self.layout.addLayout(totals_layout)
        
        self.complete_payment_btn = QPushButton("💵 إتمام وتسجيل الدفع")
        self.complete_payment_btn.setStyleSheet("background-color: #28a745; color: white; font-weight: bold; padding: 10px;")
        self.complete_payment_btn.clicked.connect(self.complete_payment)
        self.complete_payment_btn.setVisible(False)
        self.layout.addWidget(self.complete_payment_btn)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.reprint_btn = QPushButton("🖨️ إعادة طباعة الفاتورة")
        self.button_box.addButton(self.reprint_btn, QDialogButtonBox.ActionRole)
        self.button_box.accepted.connect(self.save_changes)
        self.button_box.rejected.connect(self.reject)
        self.reprint_btn.clicked.connect(self.reprint_invoice)
        self.layout.addWidget(self.button_box)
        
        self.load_invoice_data()

    def complete_payment(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("اختيار طريقة الدفع")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(f"<h3>المبلغ المستحق: {self.final_amount:.2f} {load_config()['currency_symbol']}</h3>"))
        layout.addWidget(QLabel("اختر طريقة الدفع:"))
        cash_rb = QRadioButton("💵 كاش")
        card_rb = QRadioButton("💳 بطاقة")
        cash_rb.setChecked(True)
        layout.addWidget(cash_rb)
        layout.addWidget(card_rb)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec():
            payment_method = "كاش" if cash_rb.isChecked() else "بطاقة"
            try:
                conn = sqlite3.connect(DB_NAME)
                conn.execute("UPDATE orders SET payment_status = 'Paid', payment_method = ? WHERE id = ?", (payment_method, self.order_id))
                conn.commit()
                conn.close()
                QMessageBox.information(self, "تم الدفع", "تم تحديث حالة الفاتورة إلى مدفوعة بنجاح.")
                self.load_invoice_data()
                self.reprint_invoice(ask_confirmation=False)
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل في تحديث حالة الدفع: {e}")

    def reprint_invoice(self, ask_confirmation=True):
        if ask_confirmation:
            reply = QMessageBox.question(self, "تأكيد إعادة الطباعة", "هل أنت متأكد من رغبتك في إعادة طباعة هذه الفاتورة؟", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No: return

        try:
            conn = sqlite3.connect(DB_NAME); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            order = cursor.execute("SELECT * FROM orders WHERE id = ?", (self.order_id,)).fetchone()
            if not order:
                QMessageBox.critical(self, "خطأ", f"لم يتم العثور على الفاتورة رقم {self.order_id}"); return
            items_from_db = cursor.execute("SELECT oi.quantity, p.name, oi.price_per_item, oi.id as order_item_id FROM order_items oi JOIN products p ON p.id = oi.product_id WHERE oi.order_id = ?", (self.order_id,)).fetchall()
            receipt_items = []
            for item in items_from_db:
                mods = cursor.execute("SELECT m.name, m.price_change FROM order_item_modifiers oim JOIN modifiers m ON oim.modifier_id = m.id WHERE oim.order_item_id = ?", (item['order_item_id'],)).fetchall()
                receipt_items.append({'name': item['name'], 'quantity': item['quantity'], 'item_total_price': item['price_per_item'] * item['quantity'], 'modifiers': [{'name': m['name'], 'price_change': m['price_change']} for m in mods]})
            gift_desc = None
            if order['gift_voucher_code']:
                gift_res = cursor.execute("SELECT description FROM gift_vouchers WHERE code = ?", (order['gift_voucher_code'],)).fetchone()
                if gift_res: gift_desc = gift_res['description']
            conn.close()
            receipt_details = {
                'id': order['id'], 'daily_order_number': order['daily_order_number'], 'date': order['order_date'], 
                'items': receipt_items, 'subtotal': order['total_amount'], 'discount': order['total_amount'] - order['final_amount'],
                'total': order['final_amount'], 'payment_method': order['payment_method'],
                'gift_description': gift_desc,
                'payment_status': order['payment_status']
            }
            reprint_file_path = f"receipt_{self.order_id}_reprint_{datetime.now().strftime('%H%M%S')}.pdf"
            print_receipt_full(receipt_details, [], reprint_file_path)
            QMessageBox.information(self, "تم", f"تم إرسال نسخة من الفاتورة #{order['daily_order_number']} إلى الطابعة.")
        except Exception as e:
            QMessageBox.critical(self, "خطأ فادح", f"فشل إعادة طباعة الفاتورة: {e}")

    def load_invoice_data(self):
        try:
            conn = sqlite3.connect(DB_NAME); conn.row_factory = sqlite3.Row; cursor = conn.cursor()
            order = cursor.execute("SELECT * FROM orders WHERE id = ?", (self.order_id,)).fetchone()
            if not order:
                QMessageBox.critical(self, "خطأ", f"لم يتم العثور على الفاتورة رقم {self.order_id}"); self.reject(); return

            self.is_paid = (order['payment_status'] == 'Paid')
            
            if self.is_paid:
                self.payment_status_label.setText("<h3><font color='green'>مدفوعة</font></h3>")
                self.complete_payment_btn.setVisible(False)
                self.edit_qty_btn.setEnabled(False)
                self.remove_btn.setEnabled(False)
                self.discount_input.setEnabled(False)
                self.button_box.button(QDialogButtonBox.Save).setEnabled(False)
            else:
                self.payment_status_label.setText("<h3><font color='red'>غير مدفوعة</font></h3>")
                self.complete_payment_btn.setVisible(True)
                self.edit_qty_btn.setEnabled(True)
                self.remove_btn.setEnabled(True)
                self.discount_input.setEnabled(True)
                self.button_box.button(QDialogButtonBox.Save).setEnabled(True)

            self.order_info.setText(f"طلب يومي: #{order['daily_order_number']} (ID: #{order['id']}) | تاريخ: {order['order_date']} | دفع: {order['payment_method']}")

            items = cursor.execute("SELECT oi.id, oi.product_id, p.name, oi.quantity, oi.price_per_item FROM order_items oi JOIN products p ON p.id = oi.product_id WHERE oi.order_id = ?", (self.order_id,)).fetchall()
            self.table.setRowCount(len(items))
            for row, item in enumerate(items):
                total = item['quantity'] * item['price_per_item']
                self.table.setItem(row, 0, QTableWidgetItem(str(item['id'])))
                self.table.setItem(row, 1, QTableWidgetItem(item['name']))
                self.table.setItem(row, 2, QTableWidgetItem(str(item['quantity'])))
                self.table.setItem(row, 3, QTableWidgetItem(f"{item['price_per_item']:.2f}"))
                self.table.setItem(row, 4, QTableWidgetItem(f"{total:.2f}"))

            self.subtotal = float(order['total_amount'])
            self.discount_value = self.subtotal - float(order['final_amount'])
            self.final_amount = float(order['final_amount'])

            self.subtotal_lbl.setText(f"{self.subtotal:.2f}")
            self.discount_input.setValue(self.discount_value)
            self.final_lbl.setText(f"{self.final_amount:.2f}")
            conn.close()
        except Exception as e: QMessageBox.critical(self, "خطأ في تحميل البيانات", str(e)); self.reject()

    def update_totals(self):
        self.final_amount = max(0, self.subtotal - self.discount_input.value())
        self.final_lbl.setText(f"{self.final_amount:.2f}")

    def remove_item(self):
        selected_rows = self.table.selectedIndexes()
        if not selected_rows: QMessageBox.warning(self, "تنبيه", "الرجاء تحديد عنصر للحذف"); return
        row = selected_rows[0].row(); item_id = int(self.table.item(row, 0).text()); item_name = self.table.item(row, 1).text()
        reply = QMessageBox.question(self, "تأكيد الحذف", f"هل أنت متأكد من حذف {item_name} من الفاتورة؟", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                conn = sqlite3.connect(DB_NAME); conn.execute("PRAGMA foreign_keys = ON"); conn.execute("DELETE FROM order_items WHERE id = ?", (item_id,)); conn.commit()
                self.recalculate_order_totals(conn); conn.close(); self.load_invoice_data()
                QMessageBox.information(self, "تم", f"تم حذف {item_name} من الفاتورة")
            except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل حذف العنصر: {str(e)}")

    def edit_quantity(self):
        selected_rows = self.table.selectedIndexes()
        if not selected_rows: QMessageBox.warning(self, "تنبيه", "الرجاء تحديد عنصر لتعديل الكمية"); return
        row = selected_rows[0].row(); item_id = int(self.table.item(row, 0).text()); item_name = self.table.item(row, 1).text(); current_qty = int(self.table.item(row, 2).text())
        new_qty, ok = QInputDialog.getInt(self, "تعديل الكمية", f"أدخل الكمية الجديدة لـ {item_name}:", current_qty, 1, 100, 1)
        if ok:
            try:
                conn = sqlite3.connect(DB_NAME); conn.execute("UPDATE order_items SET quantity = ? WHERE id = ?", (new_qty, item_id)); conn.commit()
                self.recalculate_order_totals(conn); conn.close(); self.load_invoice_data()
                QMessageBox.information(self, "تم", f"تم تعديل كمية {item_name} إلى {new_qty}")
            except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل تعديل الكمية: {str(e)}")

    def recalculate_order_totals(self, conn):
        cursor = conn.cursor(); result = cursor.execute("SELECT SUM(quantity * price_per_item) FROM order_items WHERE order_id = ?", (self.order_id,)).fetchone()
        new_subtotal = result[0] if result[0] else 0; 
        current_discount = self.discount_input.value()
        new_final = max(0, new_subtotal - current_discount)
        conn.execute("UPDATE orders SET total_amount = ?, final_amount = ? WHERE id = ?", (new_subtotal, new_final, self.order_id)); conn.commit()
        self.subtotal = new_subtotal
        self.final_amount = new_final

    def save_changes(self):
        if self.is_paid:
            QMessageBox.warning(self, "غير مسموح", "لا يمكن تعديل فاتورة مدفوعة.")
            return

        try:
            conn = sqlite3.connect(DB_NAME)
            self.recalculate_order_totals(conn)
            conn.close()
            QMessageBox.information(self, "تم", f"تم حفظ التعديلات على الفاتورة #{self.order_id}"); 
            self.load_invoice_data()
        except Exception as e: 
            QMessageBox.critical(self, "خطأ", f"فشل حفظ التعديلات: {str(e)}")


# ==============================================================================
# --- القسم 3.5: مكونات شاشة المطبخ (KDS) ---
# ==============================================================================

class OrderCardWidget(QFrame):
    order_completed = pyqtSignal(int, QWidget)

    def __init__(self, order_details, parent=None):
        super().__init__(parent)
        self.order_number = order_details['daily_order_number']
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)
        self.setMinimumWidth(300)
        
        # تأكد من أن حالة الدفع صحيحة عند اختيار طريقة الدفع
        if order_details.get('payment_method') and order_details.get('payment_method') != "غير محدد":
            order_details['payment_status'] = 'Paid'
        
        # إضافة علامة حالة الدفع في عنوان البطاقة
        self.payment_status = order_details.get('payment_status', 'Unpaid')
        
        # تعيين ألوان البطاقة بناءً على حالة الدفع
        if self.payment_status == 'Paid':
            card_bg_color = "#E8F5E9"  # أخضر فاتح للطلبات المدفوعة
            card_border_color = "#4CAF50"  # أخضر للحدود
        else:
            card_bg_color = "#FFECEC"  # أحمر فاتح للطلبات غير المدفوعة
            card_border_color = "#E57373"  # أحمر للحدود
            
        self.setStyleSheet(f"""
            QFrame {{ 
                background-color: {card_bg_color}; 
                border: 2px solid {card_border_color}; 
                border-radius: 10px; 
                margin: 5px;
            }}
            QLabel {{
                border: none;
                background-color: transparent;
                color: #333;
            }}
        """)
        
        layout = QVBoxLayout(self)
        
        header_layout = QHBoxLayout()
        order_num_label = QLabel(f"<b><font size='+4'>#{order_details['daily_order_number']}</font></b>")
        order_time_label = QLabel(datetime.strptime(order_details['date'], "%Y-%m-%d %H:%M:%S").strftime("%I:%M %p"))
        
        # إضافة علامة حالة الدفع في عنوان البطاقة
        payment_status_label = QLabel()
        if self.payment_status == 'Paid':
            payment_status_label.setText("<font color='green' size='+1'><b>✅ مدفوع</b></font>")
            payment_status_label.setStyleSheet("background-color: rgba(76, 175, 80, 0.2); padding: 3px; border-radius: 5px;")
        else:
            payment_status_label.setText("<font color='red' size='+1'><b>❗ غير مدفوع</b></font>")
            payment_status_label.setStyleSheet("background-color: rgba(229, 115, 115, 0.2); padding: 3px; border-radius: 5px;")
        
        header_layout.addWidget(order_num_label)
        header_layout.addWidget(payment_status_label)
        header_layout.addStretch()
        header_layout.addWidget(order_time_label)
        layout.addLayout(header_layout)
        
        line = QFrame(); line.setFrameShape(QFrame.HLine); line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        
        items_layout = QVBoxLayout()
        for item in order_details['items']:
            item_label = QLabel(f"<b>{item['quantity']}x {item['name']}</b>")
            item_label.setFont(QFont(ARABIC_FONT_NAME, 14))
            item_label.setWordWrap(True)
            items_layout.addWidget(item_label)
            
            if item.get('modifiers'):
                for mod in item['modifiers']:
                    mod_text = f"  <font color='blue'>- {mod['name']}</font>"
                    mod_label = QLabel(mod_text)
                    mod_label.setFont(QFont(ARABIC_FONT_NAME, 11))
                    items_layout.addWidget(mod_label)
        
        layout.addLayout(items_layout)
        layout.addStretch()
        
        complete_btn = QPushButton("✅ تم التحضير")
        complete_btn.setFont(QFont("Arial", 12, QFont.Bold))
        complete_btn.setStyleSheet("background-color: #28a745; color: white; padding: 8px;")
        complete_btn.clicked.connect(self.complete_order)
        layout.addWidget(complete_btn)

    def complete_order(self):
        # استدعاء API لتحديث حالة الطلب في قاعدة البيانات
        try:
            url = f"http://localhost:5000/api/complete_order/{self.order_number}"
            response = requests.post(url)
            if response.status_code == 200:
                print(f"تم تحديث حالة الطلب {self.order_number} إلى مكتمل في قاعدة البيانات")
            else:
                print(f"فشل في تحديث حالة الطلب {self.order_number}: {response.json().get('error')}")
        except Exception as e:
            print(f"خطأ في استدعاء API: {e}")
        
        # إرسال إشارة لإزالة بطاقة الطلب من شاشة المطبخ
        self.order_completed.emit(self.order_number, self)


class KitchenDisplayWindow(QMainWindow):
    order_ready_for_pickup = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("شاشة المطبخ (KDS)")
        self.setGeometry(50, 50, 1000, 700)
        self.setStyleSheet("background-color: #333;")

        self.sound_effect = QSoundEffect()
        if os.path.exists('new_order_ding.wav'):
            self.sound_effect.setSource(QUrl.fromLocalFile('new_order_ding.wav'))
            self.sound_effect.setVolume(1.0)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # إضافة شريط العنوان مع مفتاح الألوان لحالة الدفع
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #444; color: white; padding: 5px;")
        header_layout = QHBoxLayout(header_widget)
        
        title_label = QLabel("<h2>شاشة المطبخ</h2>")
        title_label.setStyleSheet("color: white;")
        header_layout.addWidget(title_label)
        
        # إضافة مفتاح الألوان لحالة الدفع
        payment_legend_layout = QHBoxLayout()
        
        legend_label = QLabel("<b>مفتاح حالة الدفع:</b>")
        legend_label.setStyleSheet("color: white; font-size: 14px;")
        payment_legend_layout.addWidget(legend_label)
        
        paid_label = QLabel("<font color='green' size='+1'><b>✅ مدفوع</b></font>")
        paid_label.setStyleSheet("background-color: rgba(76, 175, 80, 0.2); padding: 3px; border-radius: 5px; margin-right: 5px;")
        payment_legend_layout.addWidget(paid_label)
        
        unpaid_label = QLabel("<font color='red' size='+1'><b>❗ غير مدفوع</b></font>")
        unpaid_label.setStyleSheet("background-color: rgba(229, 115, 115, 0.2); padding: 3px; border-radius: 5px;")
        payment_legend_layout.addWidget(unpaid_label)
        
        payment_legend_widget = QWidget()
        payment_legend_widget.setLayout(payment_legend_layout)
        payment_legend_widget.setStyleSheet("background-color: #555; border-radius: 8px; padding: 5px;")
        
        header_layout.addStretch()
        header_layout.addWidget(payment_legend_widget)
        
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        container_widget = QWidget()
        self.order_layout = QHBoxLayout(container_widget)
        self.order_layout.setAlignment(Qt.AlignLeft)
        
        scroll_area.setWidget(container_widget)
        
        main_layout = QVBoxLayout(main_widget)
        main_layout.addWidget(header_widget)
        main_layout.addWidget(scroll_area)
        
    def add_new_order(self, order_details):
        if self.sound_effect.isLoaded():
            self.sound_effect.play()
            
        # تأكد من أن حالة الدفع صحيحة في بطاقة الطلب
        # إذا كان الكاشير قد اختار طريقة الدفع، يجب أن تظهر كمدفوعة
        if order_details.get('payment_method') and order_details.get('payment_method') != "غير محدد":
            order_details['payment_status'] = 'Paid'
        else:
            # إذا لم يتم تحديد طريقة الدفع، تأكد من أن حالة الدفع غير مدفوع
            order_details['payment_status'] = 'Unpaid'
            
        # طباعة معلومات الطلب للتصحيح
        print(f"إضافة طلب جديد #{order_details['daily_order_number']}")
        print(f"طريقة الدفع: {order_details.get('payment_method', 'غير محدد')}")
        print(f"حالة الدفع: {order_details.get('payment_status', 'غير معروف')}")
        
        # إنشاء نسخة جديدة من بيانات الطلب لتجنب مشاكل المراجع
        order_copy = order_details.copy()
            
        card = OrderCardWidget(order_copy)
        card.order_completed.connect(self.remove_order_card)
        self.order_layout.addWidget(card)
        
    def remove_order_card(self, order_number, card_widget):
        self.order_ready_for_pickup.emit(order_number)
        self.order_layout.removeWidget(card_widget)
        card_widget.deleteLater()

    def closeEvent(self, event):
        self.hide()
        event.ignore()

# ==============================================================================
# --- القسم 3.6: شاشة عرض العملاء (CDS) ---
# ==============================================================================
class CustomerDisplayWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("شاشة عرض الطلبات للعملاء")
        self.setGeometry(50, 50, 1000, 700)
        
        self.preparing_scroll_animation = None
        self.ready_scroll_animation = None

        self.config = load_config()
        self.update_config_dependent_settings()

        self.preparing_orders = {}
        self.ready_orders = {}

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        media_panel = QFrame()
        media_panel.setFrameShape(QFrame.StyledPanel)
        media_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        media_layout = QVBoxLayout(media_panel)
        
        self.media_stack = QStackedWidget()
        self.image_label = QLabel("لم يتم تحديد ملف فيديو أو صورة من الإعدادات")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setWordWrap(True)

        self.video_widget = QVideoWidget()
        self.media_player = QMediaPlayer()
        self.media_player.setVideoOutput(self.video_widget)
        self.media_player.setLoops(QMediaPlayer.Loops.Infinite)

        self.media_stack.addWidget(self.image_label)
        self.media_stack.addWidget(self.video_widget)
        media_layout.addWidget(self.media_stack)
        
        orders_panel = QFrame()
        orders_panel.setFrameShape(QFrame.StyledPanel)
        orders_panel.setMaximumWidth(450)
        orders_layout = QVBoxLayout(orders_panel)

        preparing_group = QGroupBox("🥣 قيد التجهيز")
        preparing_group_layout = QVBoxLayout(preparing_group)
        self.preparing_list_widget = QListWidget()
        self.preparing_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.preparing_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        preparing_group_layout.addWidget(self.preparing_list_widget)

        ready_group = QGroupBox("✅ جاهز للاستلام")
        ready_group_layout = QVBoxLayout(ready_group)
        self.ready_list_widget = QListWidget()
        self.ready_list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.ready_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        ready_group_layout.addWidget(self.ready_list_widget)
        
        orders_layout.addWidget(preparing_group)
        orders_layout.addWidget(ready_group)
        
        main_layout.addWidget(media_panel, 7)
        main_layout.addWidget(orders_panel, 3)

        self.update_styles()
        self.load_media()

    def update_config_dependent_settings(self):
        self.config = load_config()
        self.font_size = self.config.get('cds_font_size', 38)
        timeout_minutes = self.config.get('customer_display_timeout_minutes', 30)
        self.TIMEOUT_MS = timeout_minutes * 60 * 1000

    def update_styles(self):
        self.update_config_dependent_settings()
        
        font_family = "Tahoma, Arial"
        base_stylesheet = f"""
            QGroupBox {{
                font-family: {font_family};
                font-size: 28px;
                font-weight: bold;
                border-radius: 8px;
                margin-top: 1ex;
                padding-top: 15px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                subcontrol-position: top center;
                padding: 0 12px;
            }}
            QListWidget {{
                font-family: {font_family};
                font-size: {self.font_size}px;
                font-weight: bold;
                border: none;
                background-color: transparent;
            }}
            QListWidget::item {{
                padding: 10px;
                text-align: center;
                border-radius: 5px;
                margin: 2px 10px;
            }}
        """
        
        preparing_style = """
            QGroupBox {
                border: 2px solid #e67e22;
                color: #e67e22; /* Orange */
            }
            QListWidget::item {
                color: #ecf0f1; /* Light grey text */
                background-color: rgba(230, 126, 34, 0.2); /* Transparent orange */
            }
        """
        
        ready_style = """
            QGroupBox {
                border: 2px solid #2ecc71;
                color: #2ecc71; /* Green */
            }
            QListWidget::item {
                color: #ffffff; /* White text */
                background-color: #2ecc71; /* Solid green */
                font-weight: 900; /* Extra bold */
            }
        """

        self.setStyleSheet(base_stylesheet)
        self.preparing_list_widget.parent().setStyleSheet(preparing_style)
        self.ready_list_widget.parent().setStyleSheet(ready_style)

    def load_media(self):
        self.update_config_dependent_settings()
        media_path = self.config.get('cds_media_path', '')
        
        self.image_label.setStyleSheet("background-color: transparent;")
        self.video_widget.setStyleSheet("background-color: transparent;")

        if media_path and os.path.exists(media_path):
            file_extension = os.path.splitext(media_path)[1].lower()
            video_formats = ['.mp4', '.avi', '.mov', '.mkv']
            image_formats = ['.png', '.jpg', '.jpeg', '.bmp']
            
            if file_extension in video_formats:
                self.media_player.setSource(QUrl.fromLocalFile(media_path))
                self.media_stack.setCurrentWidget(self.video_widget)
                self.media_player.play()
            elif file_extension in image_formats:
                self.media_player.stop()
                pixmap = QPixmap(media_path)
                self.image_label.setPixmap(pixmap.scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.media_stack.setCurrentWidget(self.image_label)
            else:
                self.media_player.stop()
                self.image_label.setText(f"تنسيق الملف غير مدعوم:\n{media_path}")
                self.media_stack.setCurrentWidget(self.image_label)
        else:
            self.media_player.stop()
            self.image_label.setText(self.config.get('customer_display_promo_message', 'أهلاً وسهلاً بكم في مطعمنا'))
            self.media_stack.setCurrentWidget(self.image_label)
            self.image_label.setStyleSheet("font-size: 30px; color: #95a5a6; background-color: transparent;")

    def _setup_autoscroll(self, list_widget):
        scroll_bar = list_widget.verticalScrollBar()
        
        anim_group = QSequentialAnimationGroup(scroll_bar)
        
        scroll_down = QPropertyAnimation(scroll_bar, b"value", anim_group)
        scroll_down.setStartValue(0)
        scroll_down.setEndValue(scroll_bar.maximum())
        scroll_down.setEasingCurve(QEasingCurve.InOutCubic)
        
        pause_bottom = QPauseAnimation(anim_group)
        pause_bottom.setDuration(3000)
        
        scroll_up = QPropertyAnimation(scroll_bar, b"value", anim_group)
        scroll_up.setStartValue(scroll_bar.maximum())
        scroll_up.setEndValue(0)
        scroll_up.setEasingCurve(QEasingCurve.InOutCubic)
        
        pause_top = QPauseAnimation(anim_group)
        pause_top.setDuration(3000)

        anim_group.addAnimation(scroll_down)
        anim_group.addAnimation(pause_bottom)
        anim_group.addAnimation(scroll_up)
        anim_group.addAnimation(pause_top)
        anim_group.setLoopCount(-1)

        return anim_group

    def _update_list_autoscroll(self, list_widget, animation_attr):
        QTimer.singleShot(100, lambda: self._start_or_stop_animation(list_widget, animation_attr))
        
    def _start_or_stop_animation(self, list_widget, animation_attr):
        animation = getattr(self, animation_attr)
        scroll_bar = list_widget.verticalScrollBar()
        is_scrollable = scroll_bar.maximum() > 0

        if is_scrollable:
            if animation and animation.state() == QPropertyAnimation.Running:
                animation.stop()

            duration = max(3000, list_widget.count() * 1500)
            
            new_animation = self._setup_autoscroll(list_widget)
            new_animation.animationAt(0).setDuration(duration)
            new_animation.animationAt(2).setDuration(duration)

            setattr(self, animation_attr, new_animation)
            new_animation.start()
        else:
            if animation:
                animation.stop()
                setattr(self, animation_attr, None)
                scroll_bar.setValue(0)
    
    def add_preparing_order(self, order_details):
        order_number = order_details['daily_order_number']
        if order_number in self.preparing_orders: return 
        item = QListWidgetItem(str(order_number)); item.setTextAlignment(Qt.AlignCenter)
        self.preparing_list_widget.addItem(item)
        self.preparing_orders[order_number] = item
        self._update_list_autoscroll(self.preparing_list_widget, 'preparing_scroll_animation')

    def add_ready_order(self, order_number):
        if order_number in self.preparing_orders:
            item_to_remove = self.preparing_orders.pop(order_number)
            for i in range(self.preparing_list_widget.count()):
                if self.preparing_list_widget.item(i) == item_to_remove:
                    self.preparing_list_widget.takeItem(i); break
            self._update_list_autoscroll(self.preparing_list_widget, 'preparing_scroll_animation')

        if order_number in self.ready_orders: return 
        item = QListWidgetItem(str(order_number)); item.setTextAlignment(Qt.AlignCenter)
        self.ready_list_widget.insertItem(0, item)
        self.ready_orders[order_number] = item
        self.ready_list_widget.scrollToTop()
        self._update_list_autoscroll(self.ready_list_widget, 'ready_scroll_animation')

        self.update_config_dependent_settings()
        QTimer.singleShot(self.TIMEOUT_MS, lambda: self.remove_ready_order(order_number))

    def remove_ready_order(self, order_number):
        if order_number not in self.ready_orders: return
        item_to_remove = self.ready_orders.pop(order_number)
        for i in range(self.ready_list_widget.count()):
            if self.ready_list_widget.item(i) == item_to_remove:
                self.ready_list_widget.takeItem(i); break
        self._update_list_autoscroll(self.ready_list_widget, 'ready_scroll_animation')

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
            
    def closeEvent(self, event):
        self.media_player.stop()
        self.hide()
        event.ignore()

    def resizeEvent(self, event):
        if self.media_stack.currentWidget() == self.image_label and self.image_label.pixmap() and not self.image_label.pixmap().isNull():
             self.image_label.setPixmap(self.image_label.pixmap().scaled(self.image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        
        self._update_list_autoscroll(self.preparing_list_widget, 'preparing_scroll_animation')
        self._update_list_autoscroll(self.ready_list_widget, 'ready_scroll_animation')
        super().resizeEvent(event)
        
# ==============================================================================
# --- القسم الرابع: الواجهات الفرعية (الصفحات) ---
# ==============================================================================

class POSPageWidget(QWidget):
    def __init__(self, parent_window):
        super().__init__(); self.parent_window = parent_window
        main_layout = QHBoxLayout(self)
        menu_panel = QFrame()
        menu_panel.setFrameShape(QFrame.StyledPanel)
        
        # --- تعديل: تغيير التخطيط الرئيسي لقائمة الطعام إلى عمودي ---
        menu_layout = QVBoxLayout(menu_panel)

        # --- تعديل: إنشاء شريط علوي للأقسام ورقم الطلب ---
        top_controls_layout = QHBoxLayout()
        
        top_controls_layout.addWidget(QLabel("<b>الأقسام:</b>"))
        self.category_combo = QComboBox()
        self.category_combo.setMinimumWidth(180)
        self.category_combo.currentIndexChanged.connect(self.load_products_for_category)
        top_controls_layout.addWidget(self.category_combo)

        top_controls_layout.addStretch()

        self.next_order_label = QLabel(f"رقم الطلبية التالي: {peek_next_order_number()}")
        self.next_order_label.setStyleSheet("font-weight: bold; color: #2E86C1; font-size: 14px;")
        top_controls_layout.addWidget(self.next_order_label)

        menu_layout.addLayout(top_controls_layout)
        
        # We need a scroll area for products
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_content_widget = QWidget()
        self.menu_grid = QGridLayout(scroll_content_widget)
        scroll_area.setWidget(scroll_content_widget)
        
        menu_layout.addWidget(scroll_area)
        
        config = load_config()
        bill_ratio = config.get('pos_bill_ratio', 40) 
        menu_ratio = 100 - bill_ratio
        main_layout.addWidget(menu_panel, 55) # 55% for menu
        main_layout.addWidget(self.create_bill_panel(), 45) # 45% for bill
        
        self.load_categories()

    def load_categories(self):
        # --- تعديل: تحميل الأقسام في القائمة المنسدلة ---
        self.category_combo.clear()
        self.category_combo.addItem("الكل", "ALL")
        try:
            conn = sqlite3.connect(DB_NAME)
            categories = conn.execute("SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != '' ORDER BY category").fetchall()
            conn.close()
            for cat in categories:
                self.category_combo.addItem(cat[0], cat[0])
        except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل تحميل الأقسام: {e}")

    def load_products_for_category(self, index):
        # --- تعديل: التوافق مع إشارة القائمة المنسدلة ---
        if index == -1: return
        # Clear existing widgets from the grid
        for i in reversed(range(self.menu_grid.count())): 
            widget_to_remove = self.menu_grid.itemAt(i).widget()
            self.menu_grid.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

        category = self.category_combo.itemData(index)
        try:
            conn = sqlite3.connect(DB_NAME)
            query = "SELECT id, name, price, image_path FROM products WHERE is_available = 1"
            params = []
            if category != "ALL": query += " AND category = ?"; params.append(category)
            products = conn.execute(query, params).fetchall(); conn.close()
            row, col = 0, 0
            
            config = load_config()
            num_columns = config.get('pos_product_columns', 3)

            for p_id, name, price, img_path in products:
                btn = QPushButton(f"{name}\n({price:.2f} {load_config()['currency_symbol']})")
                btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding); btn.setFont(QFont('Arial', 12)); btn.setMinimumHeight(120)
                if img_path and os.path.exists(img_path):
                    pixmap = QPixmap(img_path)
                    if not pixmap.isNull(): scaled_pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation); btn.setIcon(QIcon(scaled_pixmap)); btn.setIconSize(QSize(80, 80))
                btn.clicked.connect(lambda _, p=(p_id, name): self.add_item_to_order(p))
                self.menu_grid.addWidget(btn, row, col); col += 1
                if col >= num_columns: 
                    col, row = 0, row + 1
        except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل تحميل المنتجات: {e}")

    def create_bill_panel(self):
        panel = QFrame(); panel.setFrameShape(QFrame.StyledPanel); layout = QVBoxLayout(panel)
        currency = load_config()['currency_symbol']

        self.bill_table = QTableWidget(); self.bill_table.setColumnCount(4); self.bill_table.setHorizontalHeaderLabels(["الكمية", "الصنف", "الإضافات", "الإجمالي"])
        self.bill_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.bill_table.setSelectionBehavior(QTableWidget.SelectRows); self.bill_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        self.bill_table.verticalHeader().setDefaultSectionSize(38)
        layout.addWidget(self.bill_table, 1)
        
        self.bill_table.model().rowsInserted.connect(self.toggle_bill_actions)

        # --- تجميع أزرار الإجراءات في صف واحد أعلى الفاتورة ---
        bill_actions_layout = QHBoxLayout()
        self.modify_item_btn = QPushButton("✏️ تعديل المحدد")
        self.modify_item_btn.clicked.connect(self.modify_selected_item)
        self.delete_item_btn = QPushButton("🗑️ حذف المحدد")
        self.delete_item_btn.clicked.connect(self.delete_selected_item)
        self.hold_btn = QPushButton("📥 تعليق الطلب")
        self.hold_btn.clicked.connect(self.hold_order)
        self.resume_btn = QPushButton("📂 استئناف طلب")
        self.resume_btn.clicked.connect(self.resume_order)
        bill_actions_layout.addWidget(self.modify_item_btn)
        bill_actions_layout.addWidget(self.delete_item_btn)
        bill_actions_layout.addWidget(self.hold_btn)
        bill_actions_layout.addWidget(self.resume_btn)
        layout.addLayout(bill_actions_layout)
        
        totals_layout = QGridLayout()
        self.subtotal_label = QLabel(f"المجموع الفرعي: 0.00 {currency}")
        self.subtotal_label.setFont(QFont("Tahoma", 14))
        self.discount_label = QLabel(f"الخصم: 0.00 {currency}")
        self.discount_label.setFont(QFont("Tahoma", 14))
        self.gift_label = QLabel("")
        self.gift_label.setFont(QFont("Tahoma", 12))
        self.total_label = QLabel(f"<h3>الإجمالي: 0.00 {currency}</h3>")
        self.total_label.setStyleSheet("font-size: 28px; font-weight: bold; color: #2ecc71; padding: 5px; border-top: 2px solid #566573;")

        totals_layout.addWidget(self.subtotal_label, 0, 0); totals_layout.addWidget(self.discount_label, 1, 0)
        totals_layout.addWidget(self.gift_label, 2, 0); totals_layout.addWidget(self.total_label, 3, 0)

        discount_frame = self.create_discount_frame()
        
        self.pay_btn = QPushButton("💰 إنهاء الطلب")
        self.pay_btn.setFont(QFont('Arial', 18, QFont.Bold))
        self.pay_btn.setMinimumHeight(70)
        self.pay_btn.setStyleSheet("background-color: #27ae60; color: white;")
        self.pay_btn.clicked.connect(self.process_checkout)
        
        self.clear_btn = QPushButton("❌ إلغاء الطلب")
        self.clear_btn.setFont(QFont('Arial', 18, QFont.Bold))
        self.clear_btn.setMinimumHeight(70)
        self.clear_btn.setStyleSheet("background-color: #c0392b; color: white;")
        self.clear_btn.clicked.connect(self.clear_order)
        
        layout.addLayout(totals_layout)
        layout.addWidget(discount_frame)
        
        main_actions_layout = QHBoxLayout()
        main_actions_layout.addWidget(self.clear_btn, 1)
        main_actions_layout.addWidget(self.pay_btn, 2)
        layout.addLayout(main_actions_layout)
        
        layout.addStretch() 
        self.toggle_bill_actions() # Initial state
        return panel

    def create_discount_frame(self):
        frame = QFrame(); frame.setFrameShape(QFrame.StyledPanel); layout = QVBoxLayout(frame)
        layout.addWidget(QLabel("تطبيق كود خصم أو هدية أو مسح فاتورة:")); self.code_input = QLineEdit()
        self.code_input.setPlaceholderText("أدخل الكود أو امسحه بالكاميرا"); btn_layout = QHBoxLayout()
        self.verify_btn = QPushButton("✔️"); self.scan_btn = QPushButton("📷"); self.auto_scan_btn = QPushButton("🔁")
        self.auto_scan_btn.setCheckable(True); self.auto_scan_btn.setToolTip("تشغيل/إيقاف المسح التلقائي المستمر")
        self.settings_btn = QPushButton("⚙️"); btn_layout.addWidget(self.verify_btn); btn_layout.addWidget(self.scan_btn)
        btn_layout.addWidget(self.auto_scan_btn); btn_layout.addWidget(self.settings_btn); self.auto_scan_status = QLabel("الحالة: -")
        self.verify_btn.clicked.connect(self.verify_code_manually); self.scan_btn.clicked.connect(self.parent_window.start_camera_scan)
        self.auto_scan_btn.clicked.connect(self.parent_window.toggle_auto_scan); self.settings_btn.clicked.connect(self.parent_window.open_camera_settings)
        layout.addWidget(self.code_input); layout.addLayout(btn_layout); layout.addWidget(self.auto_scan_status); return frame

    def toggle_bill_actions(self):
        has_items = self.bill_table.rowCount() > 0
        self.modify_item_btn.setEnabled(has_items)
        self.delete_item_btn.setEnabled(has_items)

    def add_item_to_order(self, product):
        p_id, name = product
        dialog = AddToCartDialog(p_id, name, parent=self)
        if dialog.exec():
            selection = dialog.get_selection(); 
            quantity_to_add = selection['quantity']
            mods = selection['modifiers'] # This is now a list of dicts {'id':..., 'name':..., 'price_change':...}

            # Create a unique tuple of modifier IDs for comparison
            mods_tuple = tuple(sorted(m['id'] for m in mods))

            # Find product base price
            conn = sqlite3.connect(DB_NAME)
            base_price = conn.execute("SELECT price FROM products WHERE id=?", (p_id,)).fetchone()[0]
            conn.close()
            
            # Check if an identical item (same product ID + same modifiers) is already in the order
            for item in self.parent_window.current_order:
                if item['id'] == p_id and item['mods_tuple'] == mods_tuple: 
                    item['qty'] += quantity_to_add
                    self.update_bill()
                    return

            self.parent_window.current_order.append({
                'id': p_id, 
                'name': name, 
                'base_price': base_price, 
                'qty': quantity_to_add, 
                'mods': mods, # Store list of modifier dicts
                'mods_tuple': mods_tuple # Store tuple of IDs for quick comparison
            })
            self.update_bill()

    def update_bill(self):
        if hasattr(self, 'next_order_label'): self.next_order_label.setText(f"رقم الطلبية التالي: {peek_next_order_number()}")
        config = load_config(); currency = config['currency_symbol']; discount_percentage = config['discount_percentage'] / 100.0
        self.bill_table.setRowCount(0); subtotal = 0.0
        for index, item in enumerate(self.parent_window.current_order):
            mods_price = sum(m['price_change'] for m in item['mods'])
            price_one = item['base_price'] + mods_price
            item_total = price_one * item['qty']
            subtotal += item_total
            mod_names = ", ".join([m['name'] for m in item['mods']])

            self.bill_table.insertRow(index)
            self.bill_table.setItem(index, 0, QTableWidgetItem(str(item['qty'])))
            self.bill_table.item(index, 0).setData(Qt.UserRole, index) # Store item's index in list
            self.bill_table.setItem(index, 1, QTableWidgetItem(item['name']))
            self.bill_table.setItem(index, 2, QTableWidgetItem(mod_names))
            self.bill_table.setItem(index, 3, QTableWidgetItem(f"{item_total:.2f}"))

        self.gift_label.setText(f"الهدية: {self.parent_window.gift_details['description']}" if self.parent_window.gift_details else "")
        discount = subtotal * discount_percentage if self.parent_window.discount_details else 0.0; total = subtotal - discount
        self.subtotal_label.setText(f"المجموع الفرعي: {subtotal:.2f} {currency}"); self.discount_label.setText(f"الخصم: {discount:.2f} {currency}")
        self.total_label.setText(f"<h3>الإجمالي: {total:.2f} {currency}</h3>")
        self.parent_window.order_totals = {'subtotal': subtotal, 'discount': discount, 'total': total, 'gift_description': self.parent_window.gift_details['description'] if self.parent_window.gift_details else None}

    def modify_selected_item(self):
        selected_rows = self.bill_table.selectionModel().selectedRows()
        if not selected_rows: QMessageBox.warning(self, "تنبيه", "الرجاء تحديد صنف من الفاتورة لتعديله."); return
        order_item_index = self.bill_table.item(selected_rows[0].row(), 0).data(Qt.UserRole)
        item_to_modify = self.parent_window.current_order[order_item_index]
        
        # Prepare an 'existing_item' dict for the dialog
        existing_item_for_dialog = {
            'qty': item_to_modify['qty'],
            'mods': item_to_modify['mods'] # Pass the list of modifier dicts
        }

        dialog = AddToCartDialog(item_to_modify['id'], item_to_modify['name'], existing_item=existing_item_for_dialog, parent=self)
        if dialog.exec():
            selection = dialog.get_selection()
            
            # Update item in current_order list
            self.parent_window.current_order[order_item_index]['qty'] = selection['quantity']
            self.parent_window.current_order[order_item_index]['mods'] = selection['modifiers']
            self.parent_window.current_order[order_item_index]['mods_tuple'] = tuple(sorted(m['id'] for m in selection['modifiers']))
            
            self.update_bill()

    def delete_selected_item(self):
        selected_rows = self.bill_table.selectionModel().selectedRows()
        if not selected_rows: QMessageBox.warning(self, "تنبيه", "الرجاء تحديد صنف من الفاتورة لحذفه."); return
        order_item_index = self.bill_table.item(selected_rows[0].row(), 0).data(Qt.UserRole)
        reply = QMessageBox.question(self, "تأكيد الحذف", f"هل تريد بالتأكيد حذف '{self.parent_window.current_order[order_item_index]['name']}' من الطلب؟", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes: del self.parent_window.current_order[order_item_index]; self.update_bill()

    def verify_code_manually(self):
        code = self.code_input.text().strip();
        if code: self.parent_window.process_code_verification(code)

    def process_checkout(self):
        if not self.parent_window.current_order: QMessageBox.warning(self, "تنبيه", "الفاتورة فارغة!"); return
        dialog = CheckoutDialog(self.parent_window.order_totals['total'], self)
        if dialog.exec():
            checkout_type, payment_status, payment_method_text = dialog.get_selection()
            if checkout_type:
                self.parent_window.finalize_order(payment_status, payment_method_text)

    # --- تعديل: إزالة السطر الذي يوقف المسح التلقائي ---
    def clear_order(self, silent=False):
        confirm_needed = len(self.parent_window.current_order) > 0
        if not silent and confirm_needed:
            reply = QMessageBox.question(self, "تأكيد", "هل أنت متأكد من رغبتك في إلغاء الطلب بالكامل؟", QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.No: return
        self.parent_window.current_order = []; self.parent_window.discount_details = None; self.parent_window.gift_details = None; self.parent_window.order_totals = {}; self.code_input.clear()
        # if self.parent_window.is_auto_scanning: self.parent_window.toggle_auto_scan() # <-- السطر الذي تم حذفه
        self.auto_scan_status.setText("الحالة: -"); self.update_bill()
        self.toggle_bill_actions()
        if not silent and confirm_needed: QMessageBox.information(self, "تم", "تم إلغاء الطلب الحالي.")

    def hold_order(self):
        if not self.parent_window.current_order: QMessageBox.warning(self, "تنبيه", "لا يوجد طلب حالي لتعليقه."); return
        order_snapshot = {'id': datetime.now().strftime("%H:%M:%S"), 'order_data': self.parent_window.current_order, 'discount_details': self.parent_window.discount_details, 'gift_details': self.parent_window.gift_details}
        self.parent_window.parked_orders.append(order_snapshot); self.clear_order(silent=True)
        QMessageBox.information(self, "تم", f"تم تعليق الطلب بنجاح. (ID: {order_snapshot['id']})")

    def resume_order(self):
        if not self.parent_window.parked_orders: QMessageBox.information(self, "تنبيه", "لا توجد طلبات معلَّقة."); return
        if self.parent_window.current_order:
            if QMessageBox.question(self, "تأكيد", "يوجد طلب نشط. هل تريد إلغاءه واستئناف طلب آخر؟", QMessageBox.Yes | QMessageBox.No) == QMessageBox.No: return
        dialog = ParkedOrdersDialog(self.parent_window.parked_orders, self)
        if dialog.exec():
            order_to_restore = next((o for o in self.parent_window.parked_orders if o['id'] == dialog.selected_order_id), None)
            if order_to_restore:
                self.clear_order(silent=True)
                self.parent_window.current_order = order_to_restore['order_data']; self.parent_window.discount_details = order_to_restore['discount_details']; self.parent_window.gift_details = order_to_restore['gift_details']; self.update_bill()
                self.parent_window.parked_orders.remove(order_to_restore)
                QMessageBox.information(self, "تم", f"تم استئناف الطلب {dialog.selected_order_id}.")

class SettingsPageWidget(QWidget):
    def __init__(self, parent_window):
        super().__init__(); self.parent_window = parent_window; layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>الإعدادات</h2>"))
        self.main_tabs = QTabWidget()
        layout.addWidget(self.main_tabs)
        self.main_tabs.addTab(self.create_menu_management_tab(), "إدارة قائمة الطعام")
        self.main_tabs.addTab(self.create_general_settings_tab(), "الإعدادات العامة")
        self.currently_editing_product_id = None

    def create_menu_management_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); sub_tabs = QTabWidget()
        sub_tabs.addTab(self.create_products_tab(), "المنتجات"); sub_tabs.addTab(self.create_modifiers_tab(), "الإضافات"); sub_tabs.addTab(self.create_linking_tab(), "الربط"); layout.addWidget(sub_tabs); return widget

    def create_products_tab(self):
        widget = QWidget(); main_layout = QVBoxLayout(widget)
        self.p_table = QTableWidget(0, 7); self.p_table.setHorizontalHeaderLabels(["ID", "اسم المنتج", "السعر", "القسم", "وقت التحضير (دقائق)", "مسار الصورة", "مسار الفيديو"])
        self.p_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch); self.p_table.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch); self.p_table.horizontalHeader().setSectionResizeMode(6, QHeaderView.Stretch)
        self.p_table.setSelectionBehavior(QTableWidget.SelectRows); self.p_table.setEditTriggers(QTableWidget.NoEditTriggers); self.p_table.cellClicked.connect(self.populate_form_for_editing)
        del_btn = QPushButton("❌ حذف المنتج المحدد من الجدول"); del_btn.clicked.connect(self.delete_product)
        main_layout.addWidget(QLabel("<b>قائمة المنتجات الحالية (اضغط على منتج لتعديله)</b>")); main_layout.addWidget(self.p_table); main_layout.addWidget(del_btn)
        editor_groupbox = QGroupBox("إضافة منتج جديد أو تعديل المنتج المحدد"); editor_layout = QHBoxLayout(editor_groupbox)
        form_layout = QFormLayout(); self.p_name = QLineEdit(); self.p_price = QDoubleSpinBox(); self.p_cat = QLineEdit(); self.p_prep_time = QSpinBox(); self.p_prep_time.setRange(0, 120); self.p_img_path = QLineEdit(); self.p_img_path.setReadOnly(True); self.p_video_path = QLineEdit(); self.p_video_path.setReadOnly(True)
        img_btn = QPushButton("📂 اختيار صورة..."); img_btn.clicked.connect(self.select_product_image)
        img_input_layout = QHBoxLayout(); img_input_layout.addWidget(self.p_img_path); img_input_layout.addWidget(img_btn)
        video_btn = QPushButton("📂 اختيار فيديو..."); video_btn.clicked.connect(self.select_product_video)
        video_input_layout = QHBoxLayout(); video_input_layout.addWidget(self.p_video_path); video_input_layout.addWidget(video_btn)
        form_layout.addRow("الاسم:", self.p_name); form_layout.addRow("السعر:", self.p_price); form_layout.addRow("القسم:", self.p_cat); form_layout.addRow("وقت التحضير (دقائق):", self.p_prep_time); form_layout.addRow("صورة المنتج:", img_input_layout); form_layout.addRow("فيديو المنتج:", video_input_layout)
        preview_layout = QVBoxLayout(); preview_layout.setAlignment(Qt.AlignCenter); self.p_img_preview = QLabel("معاينة الصورة"); self.p_img_preview.setFixedSize(150, 150)
        self.p_img_preview.setAlignment(Qt.AlignCenter); self.p_img_preview.setStyleSheet("border: 1px solid grey; background-color: #f0f0f0;"); preview_layout.addWidget(self.p_img_preview)
        editor_layout.addLayout(form_layout, 2); editor_layout.addLayout(preview_layout, 1); main_layout.addWidget(editor_groupbox)
        btn_layout = QHBoxLayout(); save_changes_btn = QPushButton("💾 حفظ التعديلات"); save_changes_btn.clicked.connect(self.update_product)
        add_new_btn = QPushButton("➕ إضافة كمنتج جديد"); add_new_btn.clicked.connect(self.add_product)
        clear_form_btn = QPushButton("📋 مسح النموذج"); clear_form_btn.clicked.connect(self.clear_form)
        btn_layout.addWidget(save_changes_btn); btn_layout.addWidget(add_new_btn); btn_layout.addWidget(clear_form_btn); main_layout.addLayout(btn_layout)
        self.load_products(); return widget

    def populate_form_for_editing(self, row, column):
        try:
            product_id = self.p_table.item(row, 0).text(); name = self.p_table.item(row, 1).text(); price = self.p_table.item(row, 2).text(); category = self.p_table.item(row, 3).text(); prep_time = self.p_table.item(row, 4).text(); img_path = self.p_table.item(row, 5).text(); video_path = self.p_table.item(row, 6).text() if self.p_table.item(row, 6) else ""
            self.currently_editing_product_id = int(product_id); self.p_name.setText(name); self.p_price.setValue(float(price)); self.p_cat.setText(category); self.p_prep_time.setValue(int(prep_time) if prep_time else 0); self.p_img_path.setText(img_path); self.p_video_path.setText(video_path); self.update_image_preview(img_path)
        except Exception as e: QMessageBox.warning(self, "خطأ", f"لا يمكن تحميل بيانات المنتج: {e}"); self.clear_form()

    def update_product(self):
        if self.currently_editing_product_id is None: QMessageBox.warning(self, "تنبيه", "الرجاء تحديد منتج من الجدول أولاً لتعديله."); return
        name, price = self.p_name.text().strip(), self.p_price.value(); cat, img_path = self.p_cat.text().strip(), self.p_img_path.text(); prep_time = self.p_prep_time.value(); video_path = self.p_video_path.text()
        if not name or price <= 0: QMessageBox.warning(self, "تنبيه", "اسم وسعر المنتج مطلوبان."); return
        try:
            conn = sqlite3.connect(DB_NAME)
            # التحقق من وجود عمود video_path
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(products)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'video_path' not in columns:
                # إضافة عمود video_path إذا لم يكن موجودًا
                cursor.execute('ALTER TABLE products ADD COLUMN video_path TEXT')
                conn.commit()
            
            conn.execute("UPDATE products SET name=?, price=?, category=?, preparation_time=?, image_path=?, video_path=? WHERE id=?", (name, price, cat, prep_time, img_path, video_path, self.currently_editing_product_id)); conn.commit(); conn.close()
            QMessageBox.information(self, "نجاح", f"تم تحديث المنتج '{name}' بنجاح."); self.load_products(); self.clear_form(); self.parent_window.pos_page.load_categories()
        except sqlite3.IntegrityError: QMessageBox.critical(self, "خطأ", "اسم المنتج مكرر. الرجاء اختيار اسم آخر.")
        except Exception as e: QMessageBox.critical(self, "خطأ فادح", f"فشل تحديث المنتج: {e}")

    def clear_form(self):
        self.currently_editing_product_id = None; self.p_name.clear(); self.p_price.setValue(0); self.p_cat.clear(); self.p_prep_time.setValue(0); self.p_img_path.clear(); self.p_video_path.clear()
        self.p_img_preview.setText("معاينة الصورة"); self.p_img_preview.setPixmap(QPixmap()); self.p_table.clearSelection()

    def select_product_image(self):
        f_path, _ = QFileDialog.getOpenFileName(self, "اختر صورة للمنتج", "", "Images (*.png *.jpg *.jpeg)")
        if f_path: self.p_img_path.setText(f_path); self.update_image_preview(f_path)
        
    def select_product_video(self):
        f_path, _ = QFileDialog.getOpenFileName(self, "اختر فيديو للمنتج", "", "Videos (*.mp4 *.webm *.ogg)")
        if f_path: self.p_video_path.setText(f_path)

    def update_image_preview(self, img_path):
        if img_path and os.path.exists(img_path):
            pixmap = QPixmap(img_path)
            if not pixmap.isNull(): scaled_pixmap = pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation); self.p_img_preview.setPixmap(scaled_pixmap)
            else: self.p_img_preview.setText("خطأ في تحميل الصورة"); self.p_img_preview.setPixmap(QPixmap())
        else: self.p_img_preview.setText("لا توجد صورة"); self.p_img_preview.setPixmap(QPixmap())

    def load_products(self):
        conn=sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        
        # التحقق من وجود عمود preparation_time و video_path
        cursor.execute("PRAGMA table_info(products)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'preparation_time' not in columns:
            # إضافة عمود preparation_time إذا لم يكن موجودًا
            cursor.execute('ALTER TABLE products ADD COLUMN preparation_time INTEGER DEFAULT 0')
            conn.commit()
            
        if 'video_path' not in columns:
            # إضافة عمود video_path إذا لم يكن موجودًا
            cursor.execute('ALTER TABLE products ADD COLUMN video_path TEXT')
            conn.commit()
            
        # تحميل البيانات مع مسار الفيديو
        data = conn.execute("SELECT id, name, price, category, preparation_time, image_path, video_path FROM products").fetchall()
        
        conn.close()
        self.p_table.setRowCount(0)
        for row, p_data in enumerate(data):
            self.p_table.insertRow(row)
            for col, item in enumerate(p_data): self.p_table.setItem(row, col, QTableWidgetItem(str(item) if item is not None else ""))
        self.clear_form()

    def add_product(self):
        name, price = self.p_name.text().strip(), self.p_price.value(); cat, img_path = self.p_cat.text().strip(), self.p_img_path.text(); prep_time = self.p_prep_time.value(); video_path = self.p_video_path.text()
        if not name or price <= 0: QMessageBox.warning(self, "تنبيه", "اسم وسعر المنتج مطلوبان."); return
        try:
            conn = sqlite3.connect(DB_NAME)
            # التحقق من وجود عمود video_path
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(products)")
            columns = [column[1] for column in cursor.fetchall()]
            
            if 'video_path' not in columns:
                # إضافة عمود video_path إذا لم يكن موجودًا
                cursor.execute('ALTER TABLE products ADD COLUMN video_path TEXT')
                conn.commit()
            
            conn.execute("INSERT INTO products (name, price, category, preparation_time, image_path, video_path) VALUES (?, ?, ?, ?, ?, ?)", (name, price, cat, prep_time, img_path, video_path)); conn.commit(); conn.close()
            self.load_products(); self.populate_products_for_linking(); self.clear_form(); self.parent_window.pos_page.load_categories()
            QMessageBox.information(self, "نجاح", f"تمت إضافة المنتج '{name}' بنجاح.")
        except sqlite3.IntegrityError: QMessageBox.critical(self, "خطأ", "هذا المنتج موجود بالفعل.")
        except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل إضافة المنتج: {e}")

    def delete_product(self):
        if self.p_table.currentRow() < 0: QMessageBox.warning(self, "تنبيه", "حدد منتجًا من الجدول لحذفه."); return
        p_id = self.p_table.item(self.p_table.currentRow(), 0).text(); p_name = self.p_table.item(self.p_table.currentRow(), 1).text()
        reply = QMessageBox.question(self, "تأكيد الحذف", f"هل أنت متأكد من حذف المنتج '{p_name}' بشكل نهائي؟", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            conn=sqlite3.connect(DB_NAME); conn.execute("PRAGMA foreign_keys = ON;"); conn.execute("DELETE FROM products WHERE id = ?", (p_id,)); conn.commit(); conn.close(); self.load_products(); self.populate_products_for_linking(); self.parent_window.pos_page.load_categories()

    def create_modifiers_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); self.m_table = QTableWidget(0, 3)
        self.m_table.setHorizontalHeaderLabels(["ID", "اسم الإضافة", "تغيير السعر"]); self.m_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        form = QFormLayout(); self.m_name = QLineEdit(); self.m_price = QDoubleSpinBox(); self.m_price.setRange(-1000, 1000)
        form.addRow("الاسم:", self.m_name); form.addRow("تغيير السعر:", self.m_price)
        add_btn = QPushButton("➕ إضافة"); add_btn.clicked.connect(self.add_modifier); del_btn = QPushButton("❌ حذف"); del_btn.clicked.connect(self.delete_modifier)
        layout.addWidget(self.m_table); layout.addWidget(del_btn); layout.addLayout(form); layout.addWidget(add_btn)
        self.load_modifiers(); return widget

    def create_linking_tab(self):
        widget = QWidget(); layout = QHBoxLayout(widget); p_layout = QVBoxLayout(); p_layout.addWidget(QLabel("1. اختر منتج:"))
        self.link_p_list = QListWidget(); self.link_p_list.itemClicked.connect(self.load_links_for_product)
        p_layout.addWidget(self.link_p_list); btn_layout = QVBoxLayout(); btn_layout.addStretch(); link_btn = QPushButton("➡️")
        link_btn.clicked.connect(self.link_mod); btn_layout.addWidget(link_btn); unlink_btn = QPushButton("⬅️")
        unlink_btn.clicked.connect(self.unlink_mod); btn_layout.addWidget(unlink_btn); btn_layout.addStretch()
        m_layout = QVBoxLayout(); m_layout.addWidget(QLabel("2. إضافات غير مرتبطة:")); self.unlinked_list = QListWidget()
        m_layout.addWidget(self.unlinked_list); m_layout.addWidget(QLabel("3. إضافات مرتبطة:")); self.linked_list = QListWidget()
        m_layout.addWidget(self.linked_list); layout.addLayout(p_layout, 1); layout.addLayout(btn_layout); layout.addLayout(m_layout, 2)
        self.populate_products_for_linking(); return widget

    def create_general_settings_tab(self):
        widget = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        scroll.setWidget(container)
        layout = QFormLayout(container)

        self.config = load_config()
        
        if WEB_SERVER_SUPPORT:
            web_group = QGroupBox("إعدادات المنيو الرقمي والطلب الذاتي")
            web_layout = QFormLayout(web_group)
            self.web_server_status = QLabel(f"الحالة: يعمل على http://{get_local_ip()}:5000")
            self.web_server_status.setTextInteractionFlags(Qt.TextSelectableByMouse)
            
            wifi_qr_btn = QPushButton("📲 إنشاء رمز QR للاتصال بالشبكة والمنيو")
            wifi_qr_btn.clicked.connect(self.parent_window.show_wifi_qr_generator)

            web_layout.addRow(QLabel("<b>حالة خادم الويب:</b>"), self.web_server_status)
            web_layout.addRow(wifi_qr_btn)
            layout.addRow(web_group)
        else:
            layout.addRow(QLabel("<font color='red'>مكتبة Flask غير مثبتة. ميزة المنيو الرقمي معطلة.</font>"))

        layout.addRow(QLabel("<b>إعدادات الفاتورة والمطعم</b>")); self.r_name = QLineEdit(self.config.get('restaurant_name', '')); self.r_thanks = QLineEdit(self.config.get('thank_you_message', ''))
        self.r_currency = QLineEdit(self.config.get('currency_symbol', '')); layout.addRow("اسم المطعم:", self.r_name); layout.addRow("رسالة الشكر:", self.r_thanks); layout.addRow("رمز العملة (مثال: ريال، $):", self.r_currency)
        logo_layout = QHBoxLayout(); self.r_logo_path = QLineEdit(self.config.get('logo_path', '')); logo_btn = QPushButton("📂 اختيار..."); logo_btn.clicked.connect(self.select_logo_file)
        logo_layout.addWidget(self.r_logo_path); logo_layout.addWidget(logo_btn); layout.addRow("مسار الشعار:", logo_layout)
        layout.addRow(QLabel("<b>إعدادات الخصومات والهدايا</b>")); self.issue_discounts_cb = QCheckBox("تفعيل إصدار كوبونات الخصم"); self.issue_discounts_cb.setChecked(self.config.get('issue_discounts_enabled', True))
        self.r_discount_perc = QSpinBox(); self.r_discount_perc.setRange(1, 100); self.r_discount_perc.setSuffix(" %"); self.r_discount_perc.setValue(self.config.get('discount_percentage', 25)); layout.addRow(self.issue_discounts_cb, self.r_discount_perc)
        self.issue_gifts_cb = QCheckBox("تفعيل إصدار قسائم الهدايا"); self.issue_gifts_cb.setChecked(self.config.get('issue_gifts_enabled', True))
        self.r_gift_chance = QSpinBox(); self.r_gift_chance.setRange(0, 100); self.r_gift_chance.setSuffix(" %"); self.r_gift_chance.setValue(self.config.get('gift_chance_percentage', 25)); layout.addRow(self.issue_gifts_cb, self.r_gift_chance)
        self.r_gift_desc = QLineEdit(self.config.get('default_gift_description', '')); layout.addRow("وصف الهدية الافتراضي:", self.r_gift_desc)

        layout.addRow(QLabel("<b>إعدادات متقدمة</b>"))
        reset_counter_btn = QPushButton("🔄 إعادة تعيين عداد الطلبات إلى 1 (لبدء يوم جديد)")
        reset_counter_btn.clicked.connect(reset_daily_counter)
        layout.addRow(reset_counter_btn)
        
        # أزرار مسح الطلبات
        clear_completed_btn = QPushButton("🗑️ مسح جميع الطلبات المكتملة (تم التجهيز)")
        clear_completed_btn.clicked.connect(self.clear_completed_orders)
        layout.addRow(clear_completed_btn)
        
        clear_in_progress_btn = QPushButton("🗑️ مسح جميع الطلبات قيد التجهيز")
        clear_in_progress_btn.clicked.connect(self.clear_in_progress_orders)
        layout.addRow(clear_in_progress_btn)

        layout.addRow(QLabel("<b>إعدادات شاشة عرض العميل (CDS)</b>"))

        self.cds_font_size = QSpinBox()
        self.cds_font_size.setRange(10, 100)
        self.cds_font_size.setSuffix(" بكسل")
        self.cds_font_size.setValue(self.config.get('cds_font_size', 38))
        layout.addRow("حجم خط أرقام الطلبات:", self.cds_font_size)

        self.cds_timeout = QSpinBox()
        self.cds_timeout.setRange(1, 120)
        self.cds_timeout.setSuffix(" دقيقة")
        self.cds_timeout.setValue(self.config.get('customer_display_timeout_minutes', 30))
        layout.addRow("مدة بقاء رقم الطلب على الشاشة:", self.cds_timeout)
        
        self.preparation_time = QSpinBox()
        self.preparation_time.setRange(1, 60)
        self.preparation_time.setSuffix(" دقيقة")
        self.preparation_time.setValue(self.config.get('preparation_time_minutes', 10))
        layout.addRow("وقت تجهيز الطلب:", self.preparation_time)
        
        # إضافة إعداد وقت المسح التلقائي للطلبات المجهزة
        self.auto_remove_completed_orders = QSpinBox()
        self.auto_remove_completed_orders.setRange(5, 120)
        self.auto_remove_completed_orders.setSuffix(" دقيقة")
        self.auto_remove_completed_orders.setValue(self.config.get('auto_remove_completed_orders_minutes', 20))
        layout.addRow("وقت مسح الطلبات المجهزة تلقائياً:", self.auto_remove_completed_orders)
        
        cds_media_layout = QHBoxLayout()
        self.cds_media_path = QLineEdit(self.config.get('cds_media_path', ''))
        cds_media_btn = QPushButton("📂 اختيار ملف فيديو أو صورة...")
        cds_media_btn.clicked.connect(self.select_cds_media_file)
        cds_media_layout.addWidget(self.cds_media_path)
        cds_media_layout.addWidget(cds_media_btn)
        layout.addRow("ملف العرض (فيديو/صورة):", cds_media_layout)

        self.toggle_cds_fullscreen_btn = QPushButton("🖥️ تبديل وضع ملء الشاشة لشاشة العميل")
        self.toggle_cds_fullscreen_btn.clicked.connect(self.parent_window.toggle_customer_display_fullscreen)
        layout.addRow(self.toggle_cds_fullscreen_btn)
        
        layout.addRow(QLabel("<b>إعدادات واجهة نقطة البيع</b>")) 
        
        self.pos_product_columns_spin = QSpinBox()
        self.pos_product_columns_spin.setRange(2, 6)
        self.pos_product_columns_spin.setValue(self.config.get('pos_product_columns', 3))
        layout.addRow("عدد أعمدة المنتجات:", self.pos_product_columns_spin)
        
        self.pos_bill_ratio_spin = QSpinBox()
        self.pos_bill_ratio_spin.setRange(25, 50)
        self.pos_bill_ratio_spin.setSuffix(" %")
        self.pos_bill_ratio_spin.setValue(self.config.get('pos_bill_ratio', 40))
        
        layout.addRow(QLabel("<b>إعدادات الطباعة</b>"))
        
        # إعدادات الطابعة
        if WINDOWS_PRINT_SUPPORT:
            printer_layout = QHBoxLayout()
            self.selected_printer_label = QLabel(self.config.get('selected_printer', 'الطابعة الافتراضية'))
            printer_select_btn = QPushButton("🖨️ اختيار الطابعة")
            printer_select_btn.clicked.connect(self.select_printer)
            printer_layout.addWidget(self.selected_printer_label)
            printer_layout.addWidget(printer_select_btn)
            layout.addRow("الطابعة المفضلة:", printer_layout)
        else:
            layout.addRow(QLabel("<font color='orange'>دعم الطباعة المحسن غير متاح. سيتم استخدام الطريقة العادية.</font>"))
        layout.addRow("عرض نافذة الفاتورة:", self.pos_bill_ratio_spin)
        
        layout.addRow(QLabel("<b>إعدادات المظهر</b>"))
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["الوضع الفاتح (Light)", "الوضع الداكن (Dark)"])
        current_theme = self.config.get('theme', 'light') 
        self.theme_combo.setCurrentIndex(1 if current_theme == 'dark' else 0) 
        self.theme_combo.currentIndexChanged.connect(self.parent_window.apply_theme_from_settings)
        layout.addRow("مظهر التطبيق:", self.theme_combo)
        
        layout.addRow(QLabel("<i>(بعض التغييرات تتطلب إعادة تشغيل البرنامج لتطبيقها)</i>"))

        save_btn = QPushButton("💾 حفظ كل الإعدادات"); save_btn.clicked.connect(self.save_general_settings); layout.addRow(save_btn)
        
        main_layout = QVBoxLayout(widget)
        main_layout.addWidget(scroll)
        return widget

    def select_cds_media_file(self):
        f_path, _ = QFileDialog.getOpenFileName(self, "اختر ملف فيديو أو صورة", "", "ملفات الميديا (*.mp4 *.mov *.avi *.png *.jpg *.jpeg);;كل الملفات (*.*)")
        if f_path:
            self.cds_media_path.setText(f_path)
            
    def select_logo_file(self):
        f_path, _ = QFileDialog.getOpenFileName(self, "اختر صورة", "", "Images (*.png *.jpg)");
        if f_path: self.r_logo_path.setText(f_path)
    
    def select_printer(self):
        """فتح نافذة اختيار الطابعة"""
        if not WINDOWS_PRINT_SUPPORT:
            QMessageBox.warning(self, "خطأ", "دعم الطباعة المحسن غير متاح على هذا النظام")
            return
            
        dialog = PrinterSelectionDialog(self)
        if dialog.exec() == QDialog.Accepted:
            selected_printer = dialog.get_selected_printer()
            if selected_printer:
                self.selected_printer_label.setText(selected_printer)
                # حفظ الطابعة المحددة في الإعدادات
                config = load_config()
                config['selected_printer'] = selected_printer
                with open('config.json', 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=2)
                QMessageBox.information(self, "تم الحفظ", f"تم تحديد الطابعة: {selected_printer}")

    def clear_completed_orders(self):
        """مسح جميع الطلبات المكتملة (تم التجهيز)"""
        reply = QMessageBox.question(self, "تأكيد المسح", 
                                    "هل أنت متأكد من مسح جميع الطلبات المكتملة (تم التجهيز)؟\nلا يمكن التراجع عن هذه العملية.", 
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                response = requests.post(f"http://localhost:5000/api/clear_completed_orders")
                data = response.json()
                if data.get("success"):
                    QMessageBox.information(self, "تم", data.get("message", "تم مسح الطلبات المكتملة بنجاح."))
                else:
                    QMessageBox.warning(self, "خطأ", data.get("error", "حدث خطأ أثناء مسح الطلبات المكتملة."))
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل الاتصال بالخادم: {str(e)}")
    
    def clear_in_progress_orders(self):
        """مسح جميع الطلبات قيد التجهيز"""
        reply = QMessageBox.question(self, "تأكيد المسح", 
                                    "هل أنت متأكد من مسح جميع الطلبات قيد التجهيز؟\nلا يمكن التراجع عن هذه العملية.", 
                                    QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                response = requests.post(f"http://localhost:5000/api/clear_in_progress_orders")
                data = response.json()
                if data.get("success"):
                    QMessageBox.information(self, "تم", data.get("message", "تم مسح الطلبات قيد التجهيز بنجاح."))
                else:
                    QMessageBox.warning(self, "خطأ", data.get("error", "حدث خطأ أثناء مسح الطلبات قيد التجهيز."))
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل الاتصال بالخادم: {str(e)}")
    
    def save_general_settings(self):
        theme_text = 'dark' if self.theme_combo.currentIndex() == 1 else 'light'
        self.config = {
            'restaurant_name': self.r_name.text(), 
            'thank_you_message': self.r_thanks.text(), 
            'logo_path': self.r_logo_path.text(), 
            'currency_symbol': self.r_currency.text().strip(), 
            'discount_percentage': self.r_discount_perc.value(), 
            'issue_discounts_enabled': self.issue_discounts_cb.isChecked(), 
            'issue_gifts_enabled': self.issue_gifts_cb.isChecked(), 
            'default_gift_description': self.r_gift_desc.text(), 
            'gift_chance_percentage': self.r_gift_chance.value(),
            'customer_display_timeout_minutes': self.cds_timeout.value(),
            'customer_display_promo_message': "",
            'cds_media_path': self.cds_media_path.text(),
            'cds_font_size': self.cds_font_size.value(),
            'theme': theme_text,
            'pos_product_columns': self.pos_product_columns_spin.value(),
            'pos_bill_ratio': self.pos_bill_ratio_spin.value(),
            'preparation_time_minutes': self.preparation_time.value(),
            'auto_remove_completed_orders_minutes': self.auto_remove_completed_orders.value(),
            'selected_printer': getattr(self, 'selected_printer_label', QLabel()).text() if hasattr(self, 'selected_printer_label') else 'الطابعة الافتراضية'
        }
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f: json.dump(self.config, f, ensure_ascii=False, indent=4)
        QMessageBox.information(self, "تم", "تم حفظ الإعدادات العامة.\nقد تحتاج إلى إعادة تشغيل البرنامج لتطبيق بعض التغييرات."); 
        
        self.parent_window.pos_page.load_products_for_category(self.parent_window.pos_page.category_combo.currentIndex())
        self.parent_window.pos_page.update_bill()
        self.parent_window.customer_display.update_styles()
        self.parent_window.customer_display.load_media()


    def load_modifiers(self):
        conn=sqlite3.connect(DB_NAME); data=conn.execute("SELECT id, name, price_change FROM modifiers").fetchall(); conn.close()
        self.m_table.setRowCount(0)
        for row, m_data in enumerate(data): self.m_table.insertRow(row); [self.m_table.setItem(row, col, QTableWidgetItem(str(item))) for col, item in enumerate(m_data)]

    def add_modifier(self):
        name, price = self.m_name.text().strip(), self.m_price.value()
        if not name: QMessageBox.warning(self, "تنبيه", "اسم الإضافة مطلوب."); return
        try:
            conn=sqlite3.connect(DB_NAME); conn.execute("INSERT INTO modifiers (name, price_change) VALUES (?, ?)", (name, price)); conn.commit(); conn.close()
            self.load_modifiers(); self.m_name.clear(); self.m_price.setValue(0)
        except sqlite3.IntegrityError: QMessageBox.critical(self, "خطأ", "هذه الإضافة موجودة بالفعل.")

    def delete_modifier(self):
        if self.m_table.currentRow() < 0: QMessageBox.warning(self, "تنبيه", "حدد إضافة لحذفها."); return
        m_id = self.m_table.item(self.m_table.currentRow(), 0).text()
        if QMessageBox.question(self, "تأكيد", "هل أنت متأكد؟") == QMessageBox.Yes:
            conn=sqlite3.connect(DB_NAME); conn.execute("DELETE FROM modifiers WHERE id = ?", (m_id,)); conn.commit(); conn.close(); self.load_modifiers()

    def populate_products_for_linking(self):
        self.link_p_list.clear(); self.linked_list.clear(); self.unlinked_list.clear()
        conn=sqlite3.connect(DB_NAME); data=conn.execute("SELECT id, name FROM products").fetchall(); conn.close()
        for p_id, name in data: item = QListWidgetItem(f"{name} (ID: {p_id})"); item.setData(Qt.UserRole, p_id); self.link_p_list.addItem(item)

    def load_links_for_product(self, item):
        self.linked_list.clear(); self.unlinked_list.clear(); p_id = item.data(Qt.UserRole)
        conn=sqlite3.connect(DB_NAME); all_mods = conn.execute("SELECT id, name FROM modifiers").fetchall()
        linked_ids = {r[0] for r in conn.execute("SELECT modifier_id FROM product_modifier_links WHERE product_id = ?", (p_id,)).fetchall()}; conn.close()
        for m_id, name in all_mods:
            list_item = QListWidgetItem(f"{name} (ID: {m_id})"); list_item.setData(Qt.UserRole, m_id)
            if m_id in linked_ids: self.linked_list.addItem(list_item)
            else: self.unlinked_list.addItem(list_item)

    def link_mod(self):
        p_item, m_item = self.link_p_list.currentItem(), self.unlinked_list.currentItem()
        if not p_item or not m_item: QMessageBox.warning(self, "تنبيه", "حدد منتجًا وإضافة غير مرتبطة."); return
        p_id, m_id = p_item.data(Qt.UserRole), m_item.data(Qt.UserRole)
        conn=sqlite3.connect(DB_NAME); conn.execute("INSERT OR IGNORE INTO product_modifier_links VALUES (?, ?)",(p_id,m_id)); conn.commit(); conn.close(); self.load_links_for_product(p_item)

    def unlink_mod(self):
        p_item, m_item = self.link_p_list.currentItem(), self.linked_list.currentItem()
        if not p_item or not m_item: QMessageBox.warning(self, "تنبيه", "حدد منتجًا وإضافة مرتبطة."); return
        p_id, m_id = p_item.data(Qt.UserRole), m_item.data(Qt.UserRole)
        conn=sqlite3.connect(DB_NAME); conn.execute("DELETE FROM product_modifier_links WHERE product_id = ? AND modifier_id = ?", (p_id, m_id)); conn.commit(); conn.close(); self.load_links_for_product(p_item)


class ReportsPageWidget(QWidget):
    def __init__(self, parent_window):
        super().__init__(); self.parent_window = parent_window; layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<h2>التقارير</h2>")); tabs = QTabWidget(); layout.addWidget(tabs)
        if ADVANCED_REPORTS_SUPPORT: tabs.addTab(self.create_dashboard_tab(), "لوحة المعلومات")
        tabs.addTab(self.create_sales_tab(), "التقرير المالي اليومي")
        tabs.addTab(self.create_invoices_log_tab(), "سجل الفواتير")
        tabs.addTab(self.create_products_tab(), "المنتجات")
        tabs.addTab(self.create_discounts_tab(), "الخصومات")
        tabs.addTab(self.create_gifts_tab(), "الهدايا")
        tabs.addTab(self.create_expenses_tab(), "إدارة المصاريف")

    def create_sales_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); self.calendar = QCalendarWidget()
        btn = QPushButton("📈 إنشاء التقرير المالي لليوم المحدد"); btn.clicked.connect(self.gen_financial_report)
        self.sales_display = QTextEdit(); self.sales_display.setReadOnly(True); layout.addWidget(self.calendar); layout.addWidget(btn); layout.addWidget(self.sales_display); return widget

    def create_invoices_log_tab(self):
        widget = QWidget(); layout = QHBoxLayout(widget); left_panel = QFrame(); left_layout = QVBoxLayout(left_panel)
        left_layout.addWidget(QLabel("<b>1. حدد اليوم</b>")); self.log_calendar = QCalendarWidget()
        self.log_calendar.selectionChanged.connect(self.load_invoices_for_day); self.log_invoice_list = QListWidget()
        self.log_invoice_list.itemClicked.connect(self.display_invoice_details); left_layout.addWidget(self.log_calendar); left_layout.addWidget(QLabel("<b>2. فواتير اليوم المحدد</b>")); left_layout.addWidget(self.log_invoice_list)
        invoice_actions_layout = QHBoxLayout(); self.edit_invoice_btn = QPushButton("✏️ عرض / تعديل الفاتورة"); self.delete_invoice_btn = QPushButton("🗑️ حذف الفاتورة")
        self.edit_invoice_btn.clicked.connect(self.edit_selected_invoice); self.delete_invoice_btn.clicked.connect(self.delete_selected_invoice)
        invoice_actions_layout.addWidget(self.edit_invoice_btn); invoice_actions_layout.addWidget(self.delete_invoice_btn)

        self.export_btn = QPushButton("📄 تصدير إلى Excel")
        self.export_btn.clicked.connect(self.export_invoices_to_excel)
        if not ADVANCED_REPORTS_SUPPORT: self.export_btn.setEnabled(False)
        left_layout.addLayout(invoice_actions_layout)
        left_layout.addWidget(self.export_btn)

        right_panel = QFrame(); right_layout = QVBoxLayout(right_panel); right_layout.addWidget(QLabel("<b>3. تفاصيل الفاتورة</b>"))
        self.log_invoice_details = QTextEdit(); self.log_invoice_details.setReadOnly(True); self.log_invoice_details.setFont(QFont("Courier New", 10))
        right_layout.addWidget(self.log_invoice_details); layout.addWidget(left_panel, 1); layout.addWidget(right_panel, 2); return widget

    def create_dashboard_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget)
        self.chart_calendar = QCalendarWidget()
        self.chart_calendar.selectionChanged.connect(self.update_sales_chart)
        layout.addWidget(self.chart_calendar)

        self.figure = Figure(figsize=(10, 6))
        self.canvas = FigureCanvas(self.figure)
        layout.addWidget(self.canvas)
        QTimer.singleShot(100, self.update_sales_chart)
        return widget

    def create_expenses_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form_group = QGroupBox("إضافة مصروف جديد")
        form_layout = QFormLayout(form_group)

        self.exp_desc = QLineEdit()
        self.exp_amount = QDoubleSpinBox()
        self.exp_amount.setRange(0.01, 100000.0)
        self.exp_amount.setSuffix(f" {load_config()['currency_symbol']}")
        self.exp_category = QComboBox()
        self.exp_category.addItems(["مواد أولية", "إيجار", "فواتير كهرباء وماء", "صيانة", "رواتب", "تسويق", "مصاريف أخرى"])
        self.exp_date_edit = QCalendarWidget()
        self.exp_date_edit.setSelectedDate(date.today())

        add_btn = QPushButton("➕ إضافة المصروف")
        add_btn.clicked.connect(self.add_expense)

        form_layout.addRow("الوصف:", self.exp_desc)
        form_layout.addRow("المبلغ:", self.exp_amount)
        form_layout.addRow("الفئة:", self.exp_category)
        form_layout.addRow("تاريخ الصرف:", self.exp_date_edit)
        form_layout.addRow(add_btn)

        self.expenses_table = QTableWidget()
        self.expenses_table.setColumnCount(5)
        self.expenses_table.setHorizontalHeaderLabels(["المعرف", "التاريخ", "الوصف", "الفئة", "المبلغ"])
        self.expenses_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.expenses_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.expenses_table.setEditTriggers(QTableWidget.NoEditTriggers)

        del_btn = QPushButton("🗑️ حذف المصروف المحدد")
        del_btn.clicked.connect(self.delete_expense)

        layout.addWidget(form_group)
        layout.addWidget(QLabel("<b>سجل المصاريف</b>"))
        layout.addWidget(self.expenses_table)
        layout.addWidget(del_btn)

        self.load_expenses()
        return widget

    def load_expenses(self):
        try:
            conn = sqlite3.connect(DB_NAME)
            expenses = conn.execute("SELECT id, expense_date, description, category, amount FROM expenses ORDER BY expense_date DESC").fetchall()
            conn.close()

            self.expenses_table.setRowCount(0)
            for row, data in enumerate(expenses):
                self.expenses_table.insertRow(row)
                self.expenses_table.setItem(row, 0, QTableWidgetItem(str(data[0])))
                self.expenses_table.setItem(row, 1, QTableWidgetItem(data[1]))
                self.expenses_table.setItem(row, 2, QTableWidgetItem(data[2]))
                self.expenses_table.setItem(row, 3, QTableWidgetItem(data[3]))
                self.expenses_table.setItem(row, 4, QTableWidgetItem(f"{data[4]:.2f}"))
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تحميل المصاريف: {e}")

    def add_expense(self):
        desc = self.exp_desc.text().strip()
        amount = self.exp_amount.value()
        category = self.exp_category.currentText()
        exp_date = self.exp_date_edit.selectedDate().toString("yyyy-MM-dd")

        if not desc or amount <= 0:
            QMessageBox.warning(self, "بيانات ناقصة", "الرجاء إدخال وصف ومبلغ صحيحين للمصروف.")
            return

        try:
            conn = sqlite3.connect(DB_NAME)
            conn.execute("INSERT INTO expenses (description, amount, category, expense_date) VALUES (?, ?, ?, ?)", (desc, amount, category, exp_date))
            conn.commit(); conn.close()
            QMessageBox.information(self, "تم", "تم تسجيل المصروف بنجاح.")
            self.load_expenses()
            self.exp_desc.clear()
            self.exp_amount.setValue(0.0)
        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل إضافة المصروف: {e}")

    def delete_expense(self):
        selected_rows = self.expenses_table.selectedIndexes()
        if not selected_rows:
            QMessageBox.warning(self, "تنبيه", "الرجاء تحديد مصروف من الجدول لحذفه.")
            return

        row = selected_rows[0].row()
        expense_id = self.expenses_table.item(row, 0).text()
        desc = self.expenses_table.item(row, 2).text()

        reply = QMessageBox.question(self, "تأكيد الحذف", f"هل أنت متأكد من حذف المصروف: '{desc}'؟", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                conn = sqlite3.connect(DB_NAME)
                conn.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
                conn.commit(); conn.close()
                self.load_expenses()
            except Exception as e:
                QMessageBox.critical(self, "خطأ", f"فشل حذف المصروف: {e}")

    def update_sales_chart(self):
        if not ADVANCED_REPORTS_SUPPORT: return
        selected_date = self.chart_calendar.selectedDate().toString("yyyy-MM-dd")
        conn = sqlite3.connect(DB_NAME)
        query = "SELECT STRFTIME('%H', order_date) as hour, SUM(final_amount) as total FROM orders WHERE DATE(order_date) = ? AND payment_status = 'Paid' GROUP BY hour ORDER BY hour"
        df = pd.read_sql_query(query, conn, params=(selected_date,))
        conn.close()

        self.figure.clear()
        ax = self.figure.add_subplot(111)
        if not df.empty:
            sns.barplot(x='hour', y='total', data=df, ax=ax, palette='viridis')
            ax.set_title(f"توزيع المبيعات (المدفوعة) لساعات يوم {selected_date}", family=ARABIC_FONT_NAME if ARABIC_SUPPORT else 'sans-serif', fontsize=16)
            ax.set_xlabel("الساعة", family=ARABIC_FONT_NAME if ARABIC_SUPPORT else 'sans-serif', fontsize=12)
            ax.set_ylabel(f"إجمالي المبيعات ({load_config()['currency_symbol']})", family=ARABIC_FONT_NAME if ARABIC_SUPPORT else 'sans-serif', fontsize=12)
        else:
            ax.text(0.5, 0.5, "لا توجد بيانات مبيعات مدفوعة لهذا اليوم", ha='center', va='center')
        self.canvas.draw()

    def export_invoices_to_excel(self):
        selected_date = self.log_calendar.selectedDate().toString("yyyy-MM-dd")
        file_path, _ = QFileDialog.getSaveFileName(self, "حفظ كملف Excel", f"sales_report_{selected_date}.xlsx", "Excel Files (*.xlsx)")
        if not file_path: return

        try:
            conn = sqlite3.connect(DB_NAME)
            query = """
            SELECT
                o.daily_order_number AS 'رقم الطلب اليومي', o.id AS 'معرف الفاتورة', o.order_date AS 'التاريخ والوقت',
                p.name AS 'المنتج', oi.quantity AS 'الكمية', oi.price_per_item AS 'سعر الوحدة',
                (oi.quantity * oi.price_per_item) AS 'الإجمالي الفرعي للمنتج',
                o.payment_method AS 'طريقة الدفع', o.payment_status as 'حالة الدفع', o.final_amount AS 'إجمالي الفاتورة'
            FROM orders o JOIN order_items oi ON o.id = oi.order_id JOIN products p ON oi.product_id = p.id
            WHERE DATE(o.order_date) = ? ORDER BY o.daily_order_number, p.name
            """
            df = pd.read_sql_query(query, conn, params=(selected_date,))
            conn.close()

            if df.empty:
                QMessageBox.information(self, "تنبيه", "لا توجد بيانات لتصديرها لهذا اليوم."); return

            df.to_excel(file_path, index=False, engine='openpyxl')
            QMessageBox.information(self, "نجاح", f"تم تصدير التقرير بنجاح إلى:\n{file_path}")

        except Exception as e:
            QMessageBox.critical(self, "خطأ", f"فشل تصدير الملف: {e}")

    def edit_selected_invoice(self):
        if not self.log_invoice_list.currentItem() or not self.log_invoice_list.currentItem().data(Qt.UserRole): QMessageBox.warning(self, "تنبيه", "الرجاء اختيار فاتورة لعرضها أو تعديلها."); return
        order_id = self.log_invoice_list.currentItem().data(Qt.UserRole)
        dialog = EditInvoiceDialog(order_id, self.parent_window)
        dialog.exec()
        self.load_invoices_for_day()
        self.log_invoice_details.clear()


    def delete_selected_invoice(self):
        if not self.log_invoice_list.currentItem() or not self.log_invoice_list.currentItem().data(Qt.UserRole): QMessageBox.warning(self, "تنبيه", "الرجاء اختيار فاتورة لحذفها."); return
        order_id = self.log_invoice_list.currentItem().data(Qt.UserRole)
        reply = QMessageBox.question(self, "تأكيد الحذف", f"هل أنت متأكد من حذف الفاتورة رقم {order_id} نهائياً؟\nلا يمكن التراجع عن هذه العملية.", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            try:
                conn = sqlite3.connect(DB_NAME); conn.execute("PRAGMA foreign_keys = ON"); conn.execute("DELETE FROM orders WHERE id = ?", (order_id,)); conn.commit(); conn.close()
                self.log_invoice_details.clear(); self.load_invoices_for_day(); QMessageBox.information(self, "تم", f"تم حذف الفاتورة رقم {order_id} بنجاح.")
            except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل حذف الفاتورة: {str(e)}")

    def load_invoices_for_day(self):
        self.log_invoice_list.clear(); self.log_invoice_details.clear(); date_str = self.log_calendar.selectedDate().toString("yyyy-MM-dd")
        try:
            conn=sqlite3.connect(DB_NAME)
            query = "SELECT id, daily_order_number, final_amount, TIME(order_date), payment_status FROM orders WHERE DATE(order_date) = ? ORDER BY daily_order_number DESC"
            invoices=conn.execute(query,(date_str,)).fetchall(); conn.close()
            if not invoices: self.log_invoice_list.addItem("لا توجد فواتير لهذا اليوم"); return
            for o_id, daily_num, amount, time, p_status in invoices:
                is_paid = p_status == 'Paid' or p_status == 'Completed'
                status_icon = "✔️" if is_paid else "❗"
                display_text = f"{status_icon} طلب #{daily_num} | {amount:.2f} {load_config()['currency_symbol']} | {time}"
                item=QListWidgetItem(display_text)
                if not is_paid:
                    item.setForeground(QColor('red'))
                item.setData(Qt.UserRole, o_id)
                self.log_invoice_list.addItem(item)
        except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل تحميل سجل الفواتير: {e}")

    def display_invoice_details(self, item):
        order_id = item.data(Qt.UserRole);
        if not order_id: return
        try:
            conn=sqlite3.connect(DB_NAME); conn.row_factory=sqlite3.Row; cursor=conn.cursor()
            order = cursor.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
            items = cursor.execute("SELECT oi.quantity, p.name, oi.price_per_item, oi.id as order_item_id FROM order_items oi JOIN products p ON p.id = oi.product_id WHERE oi.order_id = ?", (order_id,)).fetchall()
            
            status_text = "مدفوعة" if order['payment_status'] == 'Paid' or order['payment_status'] == 'Completed' else "غير مدفوعة"
            text = f"--- طلب يومي: #{order['daily_order_number']} (فاتورة: {order['id']}) ---\n"
            text += f"الحالة: {status_text}\n"
            text += f"تاريخ: {order['order_date']}\nدفع: {order['payment_method']}\n" + "-"*30 + "\nالأصناف:\n"
            for row in items:
                text += f"- {row['quantity']}x {row['name']} @ {row['price_per_item']:.2f}\n"
                mods = cursor.execute("SELECT m.name FROM order_item_modifiers oim JOIN modifiers m ON oim.modifier_id = m.id WHERE oim.order_item_id = ?", (row['order_item_id'],)).fetchall()
                if mods: text += f"  (إضافات: {', '.join([m['name'] for m in mods])})\n"
            text += f"\nالمجموع الفرعي: {order['total_amount']:.2f}\nالخصم: {order['total_amount'] - order['final_amount']:.2f}\n"
            if order['gift_voucher_code']:
                gift = cursor.execute("SELECT description FROM gift_vouchers WHERE code = ?", (order['gift_voucher_code'],)).fetchone()
                if gift: text += f"هدية: {gift['description']}\n"
            text += f"الإجمالي: {order['final_amount']:.2f} {load_config()['currency_symbol']}\n"; self.log_invoice_details.setText(text); conn.close()
        except Exception as e: QMessageBox.critical(self, "خطأ", f"فشل عرض تفاصيل الفاتورة: {e}")

    def gen_financial_report(self):
        date_str = self.calendar.selectedDate().toString("yyyy-MM-dd")
        currency = load_config()['currency_symbol']

        try:
            conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()

            total_paid_sales = (cursor.execute("SELECT SUM(final_amount) FROM orders WHERE DATE(order_date) = ? AND (payment_status = 'Paid' OR payment_status = 'Completed')", (date_str,)).fetchone()[0] or 0.0)
            total_unpaid_sales = (cursor.execute("SELECT SUM(final_amount) FROM orders WHERE DATE(order_date) = ? AND payment_status = 'Unpaid'", (date_str,)).fetchone()[0] or 0.0)
            
            total_discount = (cursor.execute("SELECT SUM(total_amount - final_amount) FROM orders WHERE DATE(order_date) = ?", (date_str,)).fetchone()[0] or 0.0)

            total_expenses = (cursor.execute("SELECT SUM(amount) FROM expenses WHERE expense_date = ?", (date_str,)).fetchone()[0] or 0.0)
            expenses_by_cat = cursor.execute("SELECT category, SUM(amount) FROM expenses WHERE expense_date = ? GROUP BY category", (date_str,)).fetchall()

            conn.close()

            net_cash_flow = total_paid_sales - total_expenses

            text = f"<h2>التقرير المالي ليوم: {date_str}</h2>"
            text += "<h3>ملخص المبيعات</h3>"
            text += f"<p><b><font color='darkgreen'>إجمالي المبيعات المدفوعة (المقبوضات):</font></b> {total_paid_sales:.2f} {currency}</p>"
            text += f"<p><b><font color='orange'>إجمالي المبيعات غير المدفوعة (مستحقة):</font></b> {total_unpaid_sales:.2f} {currency}</p>"
            text += f"<p><b>إجمالي الخصومات الممنوحة:</b> {total_discount:.2f} {currency}</p><hr>"

            text += "<h3>ملخص المصاريف</h3>"
            text += f"<p><b>إجمالي المصاريف:</b> {total_expenses:.2f} {currency}</p>"
            if expenses_by_cat:
                text += "<ul>"
                for cat, amount in expenses_by_cat:
                    text += f"<li>{cat}: {amount:.2f} {currency}</li>"
                text += "</ul>"
            text += "<hr>"

            profit_color = "darkgreen" if net_cash_flow >= 0 else "red"
            text += f"<h2><font color='{profit_color}'>التدفق النقدي الصافي (المقبوضات - المصاريف): {net_cash_flow:.2f} {currency}</font></h2>"

            self.sales_display.setHtml(text)

        except Exception as e:
            QMessageBox.critical(self, "خطأ في إنشاء التقرير", str(e))

    def create_products_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); btn = QPushButton("🔄 تحديث")
        btn.clicked.connect(self.gen_products_report)
        self.products_display = QTextEdit(); self.products_display.setReadOnly(True)
        layout.addWidget(btn); layout.addWidget(self.products_display); self.gen_products_report(); return widget

    def create_discounts_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); btn = QPushButton("🔄 تحديث")
        btn.clicked.connect(self.gen_discounts_report)
        self.discounts_display = QTextEdit(); self.discounts_display.setReadOnly(True)
        layout.addWidget(btn); layout.addWidget(self.discounts_display); self.gen_discounts_report(); return widget

    def create_gifts_tab(self):
        widget = QWidget(); layout = QVBoxLayout(widget); btn = QPushButton("🔄 تحديث")
        btn.clicked.connect(self.gen_gifts_report)
        self.gifts_display = QTextEdit(); self.gifts_display.setReadOnly(True)
        layout.addWidget(btn); layout.addWidget(self.gifts_display); self.gen_gifts_report(); return widget

    def gen_products_report(self):
        conn=sqlite3.connect(DB_NAME); res=conn.execute("SELECT p.name, SUM(oi.quantity) FROM order_items oi JOIN products p ON oi.product_id = p.id GROUP BY p.name ORDER BY SUM(oi.quantity) DESC").fetchall(); conn.close()
        text="--- المنتجات الأكثر مبيعاً ---\n\n" + "\n".join([f"- {name}: {qty} مرة" for name, qty in res]); self.products_display.setText(text)

    def gen_discounts_report(self):
        conn=sqlite3.connect(DB_NAME); total, used = conn.execute("SELECT COUNT(*) FROM discount_codes").fetchone()[0], conn.execute("SELECT COUNT(*) FROM discount_codes WHERE status = 'مُستخدم'").fetchone()[0]; conn.close()
        rate=(used/total*100) if total > 0 else 0; text=f"--- تقرير الخصومات ---\n\n- إجمالي الأكواد: {total}\n- المستخدمة: {used}\n- نسبة الاستخدام: {rate:.2f}%"; self.discounts_display.setText(text)

    def gen_gifts_report(self):
        conn=sqlite3.connect(DB_NAME); total, used = conn.execute("SELECT COUNT(*) FROM gift_vouchers").fetchone()[0], conn.execute("SELECT COUNT(*) FROM gift_vouchers WHERE status = 'مُستخدم'").fetchone()[0]; conn.close()
        rate=(used/total*100) if total > 0 else 0; text=f"--- تقرير الهدايا ---\n\n- إجمالي القسائم: {total}\n- المستخدمة: {used}\n- نسبة الاستخدام: {rate:.2f}%"; self.gifts_display.setText(text)

# ==============================================================================
# --- القسم الخامس: النافذة الرئيسية للتطبيق (القلب) ---
# ==============================================================================

class FoodTruckApp(QMainWindow):
    new_order_for_kitchen = pyqtSignal(dict)
    new_order_for_customer_display = pyqtSignal(dict)
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle('منظومة إدارة مطعم متنقل')
        self.setGeometry(100, 100, 1200, 800)
        self.parked_orders = []
        self.current_order = []
        self.discount_details = None
        self.gift_details = None
        self.order_totals = {}
        self.camera_thread = None
        self.is_auto_scanning = False
        self.active_camera_index = self.load_camera_setting()
        self.last_scanned_code = None

        # تم نقل شريط التنقل إلى شريط أدوات
        self.create_navigation_toolbar()
        
        self.stacked_widget = QStackedWidget()
        self.setCentralWidget(self.stacked_widget)


        self.pos_page = POSPageWidget(self)
        self.settings_page = SettingsPageWidget(self)
        self.reports_page = ReportsPageWidget(self)
        self.stacked_widget.addWidget(self.pos_page)
        self.stacked_widget.addWidget(self.settings_page)
        self.stacked_widget.addWidget(self.reports_page)
        
        self.kitchen_display = KitchenDisplayWindow()
        self.customer_display = CustomerDisplayWindow()

        self.apply_theme_from_config()

        self.pos_btn.clicked.connect(self.switch_to_pos)
        self.reports_btn.clicked.connect(self.switch_to_reports)
        self.menu_management_btn.clicked.connect(self.switch_to_menu_management)
        self.settings_btn.clicked.connect(self.switch_to_settings)
        self.kds_btn.clicked.connect(self.show_kds_window)
        self.cds_btn.clicked.connect(self.show_cds_window)
        
        self.new_order_for_kitchen.connect(self.kitchen_display.add_new_order)
        self.new_order_for_customer_display.connect(self.customer_display.add_preparing_order)
        self.kitchen_display.order_ready_for_pickup.connect(self.customer_display.add_ready_order)
        
        if WEB_SERVER_SUPPORT:
            self.web_server_thread = threading.Thread(target=run_flask_in_thread, daemon=True)
            self.web_server_thread.start()
        
        self.switch_to_pos()

    def create_navigation_toolbar(self):
        nav_toolbar = self.addToolBar("Main Navigation")
        nav_toolbar.setObjectName("NavToolBar")
        nav_toolbar.setMovable(False)

        self.pos_btn = QPushButton("💰 نقطة البيع")
        self.reports_btn = QPushButton("📊 التقارير")
        self.menu_management_btn = QPushButton("📋 إدارة الأقسام")
        self.settings_btn = QPushButton("⚙️ الإعدادات العامة")

        self.nav_button_group = QButtonGroup(self)
        self.nav_button_group.setExclusive(True)

        for btn in [self.pos_btn, self.reports_btn, self.menu_management_btn, self.settings_btn]:
            btn.setCheckable(True)
            self.nav_button_group.addButton(btn)
            nav_toolbar.addWidget(btn)

        nav_toolbar.addSeparator()

        self.kds_btn = QPushButton("📺 شاشة المطبخ")
        self.cds_btn = QPushButton("🖥️ شاشة العميل")
        for btn in [self.kds_btn, self.cds_btn]:
            nav_toolbar.addWidget(btn)

        self.addToolBar(Qt.TopToolBarArea, nav_toolbar)

    def show_wifi_qr_generator(self):
        dialog = WifiQRGeneratorDialog(self)
        dialog.exec()

    def apply_theme_from_config(self):
        config = load_config()
        theme = config.get('theme', 'light')
        if theme == 'dark':
            app.setStyleSheet(DARK_THEME_STYLESHEET)
            self.customer_display.setStyleSheet("")
            self.kitchen_display.setStyleSheet("background-color: #333;")
        else:
            app.setStyleSheet(LIGHT_THEME_STYLESHEET)
            self.customer_display.setStyleSheet("")
            self.kitchen_display.setStyleSheet("background-color: #F5F5F5;")
        self.customer_display.update_styles()
            
    def apply_theme_from_settings(self, index):
        if index == 1:
             app.setStyleSheet(DARK_THEME_STYLESHEET)
             self.kitchen_display.setStyleSheet("background-color: #333;")
        else:
             app.setStyleSheet(LIGHT_THEME_STYLESHEET)
             self.kitchen_display.setStyleSheet("background-color: #F5F5F5;")
        
        self.customer_display.setStyleSheet("")
        self.customer_display.update_styles()
    
    def show_kds_window(self):
        if self.kitchen_display.isHidden():
            self.kitchen_display.show()
        else:
            self.kitchen_display.activateWindow()
            
    def show_cds_window(self):
        self.customer_display.update_styles()
        self.customer_display.load_media() 
        
        screens = QApplication.screens()
        if len(screens) > 1 and self.customer_display.isHidden():
            dialog = ScreenSelectionDialog(screens, self)
            if dialog.exec():
                selected_screen_index = dialog.selected_screen_index
                if selected_screen_index != -1:
                    screen_geometry = screens[selected_screen_index].geometry()
                    self.customer_display.move(screen_geometry.topLeft())
                    self.customer_display.showMaximized()
            else:
                return
        else:
            if self.customer_display.isHidden():
                self.customer_display.showMaximized()
            else:
                self.customer_display.activateWindow()

    def toggle_customer_display_fullscreen(self):
        if not self.customer_display.isVisible():
            self.show_cds_window()
            QTimer.singleShot(100, self.customer_display.toggle_fullscreen)
        else:
            self.customer_display.toggle_fullscreen()
            
    def switch_to_pos(self):
        self.pos_page.update_bill()
        self.stacked_widget.setCurrentWidget(self.pos_page)
        self.pos_btn.setChecked(True)

    def switch_to_menu_management(self):
        self.settings_page.load_products()
        self.settings_page.load_modifiers()
        self.settings_page.populate_products_for_linking()
        self.stacked_widget.setCurrentWidget(self.settings_page)
        self.settings_page.main_tabs.setCurrentIndex(0)
        self.menu_management_btn.setChecked(True)

    def switch_to_settings(self):
        self.settings_page.load_products()
        self.settings_page.load_modifiers()
        self.settings_page.populate_products_for_linking()
        self.stacked_widget.setCurrentWidget(self.settings_page)
        self.settings_page.main_tabs.setCurrentIndex(1)
        self.settings_btn.setChecked(True)

    def switch_to_reports(self):
        self.reports_page.load_invoices_for_day()
        self.reports_page.load_expenses()
        if ADVANCED_REPORTS_SUPPORT: self.reports_page.update_sales_chart()
        self.stacked_widget.setCurrentWidget(self.reports_page)
        self.reports_btn.setChecked(True)

    def finalize_order(self, payment_status, payment_method):
        if not self.current_order:
            QMessageBox.warning(self, "خطأ", "لا يمكن حفظ طلب فارغ.")
            return
        
        # تأكد من أن حالة الدفع صحيحة عند اختيار طريقة الدفع
        # إذا كان المستخدم قد اختار طريقة دفع، فيجب أن تكون الحالة "مدفوعة"
        if payment_method and payment_method != "غير محدد" and payment_method != "دفع لاحقاً":
            payment_status = 'Paid'
        else:
            # إذا كان الدفع لاحقاً، تأكد من أن حالة الدفع غير مدفوع
            payment_status = 'Unpaid'
        
        conn = None
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            conn.execute("PRAGMA foreign_keys = ON;")
            cursor.execute("BEGIN TRANSACTION;")

            daily_order_num = get_next_order_number(cursor)
            time_now = datetime.now()
            time_str = time_now.strftime("%Y-%m-%d %H:%M:%S")

            discount_id = self.discount_details['id'] if self.discount_details else None
            gift_code = self.gift_details['code'] if self.gift_details else None

            cursor.execute(
                "INSERT INTO orders (daily_order_number, order_date, total_amount, discount_code_id, final_amount, payment_method, gift_voucher_code, payment_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (daily_order_num, time_str, self.order_totals['subtotal'], discount_id, self.order_totals['total'], payment_method, gift_code, payment_status))

            order_id = cursor.lastrowid

            for item in self.current_order:
                price_one = item['base_price'] + sum(m['price_change'] for m in item['mods'])
                cursor.execute("INSERT INTO order_items (order_id, product_id, quantity, price_per_item) VALUES (?, ?, ?, ?)",
                               (order_id, item['id'], item['qty'], price_one))
                item_id = cursor.lastrowid
                for mod_data in item['mods']:
                    cursor.execute("INSERT INTO order_item_modifiers (order_item_id, modifier_id) VALUES (?, ?)", (item_id, mod_data['id']))

            if discount_id:
                cursor.execute("UPDATE discount_codes SET status = 'مُستخدم', usage_date = ? WHERE id = ?", (time_str, discount_id))
            if gift_code:
                cursor.execute("UPDATE gift_vouchers SET status = 'مُستخدم', usage_date = ? WHERE code = ?", (time_str, gift_code))

            receipt_items = [
                {'name': item['name'], 'quantity': item['qty'], 
                 'modifiers': [{'name': m['name'], 'price_change': m['price_change']} for m in item['mods']], 
                 'item_total_price': (item['base_price'] + sum(m['price_change'] for m in item['mods'])) * item['qty']} 
                for item in self.current_order
            ]
            receipt_details = {
                'id': order_id, 'daily_order_number': daily_order_num, 'date': time_str, 'items': receipt_items, 
                **self.order_totals, 'payment_method': payment_method, 'payment_status': payment_status
            }

            config = load_config()
            issues_to_print = []
            if payment_status == 'Paid':
                if config.get('issue_gifts_enabled', False) and random.randint(1, 100) <= config.get('gift_chance_percentage', 25):
                    gift_details = self.generate_new_gift_voucher(cursor, config.get('default_gift_description', 'هدية'))
                    if gift_details: issues_to_print.append(gift_details)
                if config.get('issue_discounts_enabled', False):
                    discount_details = self.generate_new_coupon(cursor)
                    if discount_details: issues_to_print.append(discount_details)

            conn.commit()
            self.new_order_for_kitchen.emit(receipt_details)
            if payment_status == 'Paid':
                self.new_order_for_customer_display.emit(receipt_details)
            receipt_path = f"receipt_{order_id}.pdf"
            kitchen_path = f"kitchen_ticket_{order_id}.pdf"
            print_receipt_full(receipt_details, issues_to_print, receipt_path)
            print_kitchen_ticket_enhanced(receipt_details, kitchen_path)
            QMessageBox.information(self, "تم", f"تم حفظ الطلب #{daily_order_num} وطباعته بنجاح!")
            self.pos_page.clear_order(silent=True)
        except Exception as e:
            if conn: conn.rollback()
            QMessageBox.critical(self, "خطأ فادح", f"فشل حفظ الطلب:\n{e}\n\nتم التراجع عن العملية.")
        finally:
            if conn: conn.close()

    def generate_new_coupon(self, cursor):
        code = 'D-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
        try:
            qr_path = f"qr_discount_{code}.png"; qrcode.make(code).save(qr_path)
            cursor.execute("INSERT INTO discount_codes (code, status, creation_date) VALUES (?, ?, ?)", (code, 'غير مُستخدم', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            return {'type': 'discount', 'code': code, 'qr_path': qr_path}
        except sqlite3.IntegrityError: return self.generate_new_coupon(cursor)
    def generate_new_gift_voucher(self, cursor, description):
        code = 'GIFT-' + ''.join(random.choices(string.digits, k=8))
        try:
            qr_path = f"qr_gift_{code}.png"; qrcode.make(code).save(qr_path)
            cursor.execute("INSERT INTO gift_vouchers (code, description, status, creation_date) VALUES (?, ?, ?, ?)", (code, description, 'صالح', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            return {'type': 'gift', 'code': code, 'qr_path': qr_path, 'description': description}
        except sqlite3.IntegrityError: return self.generate_new_gift_voucher(cursor, description)

    def _handle_invoice_scan(self, code):
        """Attempts to process the code as an invoice barcode. Returns True if handled."""
        try:
            decoded_bytes = base64.b64decode(code)
            decoded_str = decoded_bytes.decode('utf-8')
            if not decoded_str.startswith("INVOICE-"): return False

            parts = decoded_str.split('-')
            if len(parts) < 5: raise ValueError("Invalid invoice barcode format")
            
            date_part = f"{parts[1]}-{parts[2]}-{parts[3]}"
            daily_num_part = parts[4]

            conn = sqlite3.connect(DB_NAME)
            conn.row_factory = sqlite3.Row
            # تحسين الاستعلام للتحقق من حالة الدفع وتفاصيل أكثر
            res = conn.execute(
                """SELECT o.id, o.payment_status, o.final_amount, o.payment_method, 
                   COUNT(oi.id) as item_count, o.daily_order_number
                   FROM orders o 
                   LEFT JOIN order_items oi ON o.id = oi.order_id
                   WHERE o.daily_order_number = ? AND DATE(o.order_date) = ?
                   GROUP BY o.id""", 
                (daily_num_part, date_part)
            ).fetchone()
            
            if res:
                order_id = res['id']
                payment_status = res['payment_status']
                final_amount = res['final_amount']
                payment_method = res['payment_method'] or "غير محدد"
                item_count = res['item_count']
                daily_number = res['daily_order_number']
                
                # إضافة رسالة توضح حالة الدفع بشكل أكثر تفصيلاً
                status_emoji = "✅" if payment_status == "Paid" else "⚠️"
                status_text = "مدفوعة" if payment_status == "Paid" else "غير مدفوعة"
                status_color = "green" if payment_status == "Paid" else "red"
                
                # عرض رسالة أكثر تفصيلاً للمستخدم
                self.pos_page.auto_scan_status.setText(
                    f"<span style='color:{status_color};'>{status_emoji} فاتورة #{daily_number}</span> "
                    f"({status_text}) - {item_count} صنف - {final_amount:.2f} ريال"
                )
                QApplication.processEvents()
                
                # فتح نافذة تعديل الفاتورة
                edit_dialog = EditInvoiceDialog(order_id, self)
                
                # إذا كانت الفاتورة غير مدفوعة، نقوم بتنبيه المستخدم بشكل واضح
                if payment_status != "Paid":
                    QTimer.singleShot(100, lambda: QMessageBox.warning(
                        edit_dialog, 
                        "تنبيه: فاتورة غير مدفوعة", 
                        f"<h3 style='color:red;'>الفاتورة رقم {daily_number} غير مدفوعة</h3>"
                        f"<p>المبلغ المستحق: <b>{final_amount:.2f} ريال</b></p>"
                        f"<p>عدد الأصناف: {item_count}</p>"
                        f"<p>يرجى استكمال عملية الدفع من خلال الضغط على زر 'إكمال الدفع'.</p>"
                    ))
                
                edit_dialog.exec()
                
                # تحديث الرسالة بعد إغلاق النافذة
                if payment_status != "Paid":
                    # التحقق من حالة الدفع بعد إغلاق النافذة
                    updated_status = conn.execute(
                        "SELECT payment_status FROM orders WHERE id = ?", (order_id,)
                    ).fetchone()
                    
                    if updated_status and updated_status[0] == "Paid":
                        self.pos_page.auto_scan_status.setText(f"✅ تم دفع الفاتورة #{daily_number} بنجاح!")
                    else:
                        self.pos_page.auto_scan_status.setText(f"⚠️ الفاتورة #{daily_number} لا تزال غير مدفوعة")
                
                conn.close()
                return True
            else:
                self.pos_page.auto_scan_status.setText("⚠️ باركود فاتورة، ولكن غير موجودة في قاعدة البيانات.")
                conn.close()
                return True # It was an invoice code, but invalid. Consider it handled.
        except (ValueError, TypeError, IndexError, base64.binascii.Error) as e:
            self.pos_page.auto_scan_status.setText(f"❌ خطأ في قراءة باركود الفاتورة: {str(e)}")
            return False # Not a valid invoice barcode, continue checks.

    def _handle_temp_order_scan(self, code):
        """Attempts to fetch a temporary order from the server. Returns True if handled."""
        if not (4 <= len(code) <= 10 and code.isalnum() and not code.startswith(('D-', 'GIFT-'))):
            return False # Not a temp ID format, let other handlers try
        try:
            ip_addr = get_local_ip()
            url = f"http://{ip_addr}:5000/api/get_order/{code}"
            with urllib.request.urlopen(url, timeout=5) as response:
                if response.status == 200:
                    order_data = json.loads(response.read().decode('utf-8'))
                    self.load_customer_order(order_data)
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.pos_page.auto_scan_status.setText(f"⚠️ Order #{code} not found or already used.")
            else:
                self.pos_page.auto_scan_status.setText(f"❌ Network Error: {e.code}")
        except Exception as e:
            self.pos_page.auto_scan_status.setText("❌ Failed to connect to server.")
            print(f"Error fetching temp order: {e}")
        return True # It looked like a temp ID but an error occurred. Consider it handled.

    def _handle_webapp_order_scan(self, code):
        """Attempts to process the code as a full JSON order. Returns True if handled."""
        try:
            order_data = json.loads(code)
            if isinstance(order_data, dict) and order_data.get('source') == 'WebApp' and 'items' in order_data:
                self.load_customer_order(order_data)
                return True
            return False
        except (json.JSONDecodeError, TypeError):
            return False

    def _handle_coupon_scan(self, code):
        """Attempts to process the code as a discount/gift coupon. Returns True if handled."""
        try:
            conn = sqlite3.connect(DB_NAME)
            discount = conn.execute("SELECT id, status FROM discount_codes WHERE code = ?", (code,)).fetchone()
            if discount:
                if discount[1] == 'غير مُستخدم':
                    self.discount_details = {'id': discount[0]}; self.pos_page.auto_scan_status.setText("✅ Discount coupon applied!"); return True
                else:
                    self.pos_page.auto_scan_status.setText("⚠️ Discount coupon already used."); return True
            gift = conn.execute("SELECT code, description, status FROM gift_vouchers WHERE code = ?", (code,)).fetchone()
            if gift:
                if gift[2] == 'صالح':
                    self.gift_details = {'code': gift[0], 'description': gift[1]}; self.pos_page.auto_scan_status.setText(f"✅ Gift voucher applied: {gift[1]}!"); return True
                else:
                    self.pos_page.auto_scan_status.setText("⚠️ Gift voucher is invalid/used."); return True
            return False
        except Exception as e:
            self.pos_page.auto_scan_status.setText(f"❌ Error during verification: {e}"); return True
        finally:
            conn.close()

    def process_code_verification(self, code):
        code = code.strip()
        if not code or (self.is_auto_scanning and code == self.last_scanned_code): return
        self.last_scanned_code = code; self.pos_page.code_input.setText(code)
        self.pos_page.auto_scan_status.setText(f"جاري التحقق من: {code[:30]}...")
        QApplication.processEvents()

        if self._handle_temp_order_scan(code):
            pass
        elif self._handle_invoice_scan(code):
            pass
        elif self._handle_webapp_order_scan(code):
            pass
        elif self._handle_coupon_scan(code):
            self.pos_page.code_input.clear(); self.pos_page.update_bill()
        else:
            if not self.pos_page.auto_scan_status.text().startswith(("⚠️", "❌", "✅")):
                self.pos_page.auto_scan_status.setText("كود غير معروف أو غير صالح.")

        self.pos_page.code_input.clear()
        QTimer.singleShot(4000, lambda: (self.pos_page.auto_scan_status.setText("الحالة: -"), setattr(self, 'last_scanned_code', None)))

    # --- الحل البرمجي: دالة معدلة ومحسنة لتحميل الطلب ---
    def load_customer_order(self, order_data):
        """ 
        يقوم بتحميل الطلب من المنيو الرقمي مع التحقق من صحة ارتباط الإضافات بالمنتجات.
        إذا كانت هناك إضافة غير صالحة، يتم تجاهلها مع عرض تحذير للكاشير.
        تم تحسين الدالة للتعامل بشكل أفضل مع الطلبات من شاشة العميل ومسح الباركود.
        """
        # عرض رسالة توضح أنه جاري معالجة الطلب
        self.pos_page.auto_scan_status.setText("⏳ جاري معالجة الطلب من شاشة العميل...")
        QApplication.processEvents()
        
        # مسح الطلب الحالي
        self.pos_page.clear_order(silent=True)
        
        conn = None
        try:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            
            temp_order_list = []
            warning_messages = []

            all_products_db = {p[0]: {'name': p[1], 'price': p[2]} for p in cursor.execute("SELECT id, name, price FROM products WHERE is_available = 1")}
            all_modifiers_db = {m[0]: {'name': m[1], 'price_change': m[2]} for m in cursor.execute("SELECT id, name, price_change FROM modifiers")}
            
            # جلب جميع الروابط مرة واحدة لتحسين الأداء
            product_modifier_links = {}
            for p_id_link, m_id_link in cursor.execute("SELECT product_id, modifier_id FROM product_modifier_links"):
                product_modifier_links.setdefault(p_id_link, set()).add(m_id_link)

            for item_from_customer in order_data.get('items', []):
                p_id = item_from_customer.get('id')
                qty = item_from_customer.get('qty', 0)
                requested_mod_ids = item_from_customer.get('modifiers', [])
                
                if p_id not in all_products_db or not isinstance(qty, int) or qty <= 0: warning_messages.append(f"منتج بمعرف {p_id} غير موجود أو غير متاح."); continue

                product_details = all_products_db[p_id]
                selected_mods_data = []
                valid_modifier_ids_for_product = product_modifier_links.get(p_id, set())
                
                for mod_id in requested_mod_ids:
                    if mod_id in valid_modifier_ids_for_product and mod_id in all_modifiers_db:
                        mod_info = all_modifiers_db[mod_id]
                        selected_mods_data.append({
                            'id': mod_id, 
                            'name': mod_info['name'], 
                            'price_change': mod_info['price_change']
                        })
                    else:
                        mod_name = all_modifiers_db.get(mod_id, {}).get('name', f"ID: {mod_id}")
                        warning_messages.append(f"تم تجاهل الإضافة '{mod_name}' للمنتج '{product_details['name']}' لأنها غير متاحة له.")

                mods_tuple = tuple(sorted(m['id'] for m in selected_mods_data))
                
                temp_order_list.append({
                    'id': p_id, 
                    'name': product_details['name'], 
                    'base_price': product_details['price'], 
                    'qty': qty, 
                    'mods': selected_mods_data, 
                    'mods_tuple': mods_tuple
                })
            
            conn.close()

            if temp_order_list:
                final_order = {}
                for item in temp_order_list:
                    key = (item['id'], item['mods_tuple']) 
                    if key in final_order:
                        final_order[key]['qty'] += item['qty']
                    else:
                        final_order[key] = item
                
                self.current_order = list(final_order.values())
                self.pos_page.update_bill()
                
                # حساب إجمالي الطلب والعناصر
                total_items = sum(item['qty'] for item in final_order.values())
                total_amount = sum(item['base_price'] * item['qty'] + 
                                  sum(mod['price_change'] * item['qty'] for mod in item['mods']) 
                                  for item in final_order.values())
                
                # عرض رسالة نجاح مفصلة
                status_msg = f"✅ تم تحميل طلب العميل بنجاح! ({total_items} صنف، {total_amount:.2f} ريال)"
                
                # إظهار تفاصيل الطلب في نافذة منبثقة
                order_details = f"<h3>تفاصيل الطلب من شاشة العميل</h3>"
                order_details += f"<p><b>عدد الأصناف:</b> {total_items}</p>"
                order_details += f"<p><b>المبلغ الإجمالي:</b> {total_amount:.2f} ريال</p>"
                order_details += "<p><b>الأصناف:</b></p><ul>"
                
                for item in final_order.values():
                    item_total = item['base_price'] * item['qty'] + sum(mod['price_change'] * item['qty'] for mod in item['mods'])
                    order_details += f"<li>{item['name']} × {item['qty']} = {item_total:.2f} ريال"
                    if item['mods']:
                        order_details += "<ul>"
                        for mod in item['mods']:
                            order_details += f"<li>{mod['name']} ({mod['price_change']:+.2f} ريال)</li>"
                        order_details += "</ul>"
                    order_details += "</li>"
                order_details += "</ul>"
                
                if warning_messages:
                    order_details += "<p><b>ملاحظات:</b></p><ul>"
                    for msg in warning_messages:
                        order_details += f"<li>{msg}</li>"
                    order_details += "</ul>"
                    order_details += "<p>الرجاء مراجعة الفاتورة مع العميل.</p>"
                    
                    # عرض التحذيرات في نافذة منبثقة
                    QMessageBox.information(self, "تم استلام طلب من شاشة العميل", order_details)
                else:
                    # عرض تفاصيل الطلب في نافذة منبثقة بدون تحذيرات
                    QMessageBox.information(self, "تم استلام طلب من شاشة العميل", order_details)
            else:
                self.pos_page.clear_order(silent=True)
                status_msg = "❌ فشل تحميل الطلب. جميع المنتجات كانت غير صالحة أو غير متوفرة."

            self.pos_page.auto_scan_status.setText(status_msg)
            QTimer.singleShot(5000, lambda: self.pos_page.auto_scan_status.setText("الحالة: -"))

        except Exception as e:
            if conn: conn.close()
            self.pos_page.auto_scan_status.setText(f"فشل تحميل طلب العميل: {e}")
            QTimer.singleShot(5000, lambda: self.pos_page.auto_scan_status.setText("الحالة: -"))

    def load_camera_setting(self):
        try:
            with open(CAMERA_CONFIG_FILE, 'r') as f: return int(f.read().strip())
        except: return 0
    def save_camera_setting(self, index):
        self.active_camera_index = index;
        with open(CAMERA_CONFIG_FILE, 'w') as f: f.write(str(index))
        QMessageBox.information(self, "تم", f"تم تحديد الكاميرا {index}.")
    def open_camera_settings(self):
        dialog = CameraSettingsDialog(self.active_camera_index, self); dialog.saved.connect(self.save_camera_setting); dialog.exec()
    
    def start_camera_scan(self, continuous=False):
        if self.camera_thread and self.camera_thread.isRunning(): return
        self.last_scanned_code = None; self.pos_page.scan_btn.setEnabled(False); self.camera_thread = CameraThread(self.active_camera_index, continuous, self)
        self.camera_thread.code_found.connect(self.process_code_verification); self.camera_thread.finished.connect(lambda: self.pos_page.scan_btn.setEnabled(True))
        self.camera_thread.error_found.connect(self.handle_camera_error); self.camera_thread.start()

    def toggle_auto_scan(self):
        if self.is_auto_scanning:
            self.is_auto_scanning = False; self.pos_page.auto_scan_btn.setChecked(False); self.pos_page.auto_scan_status.setText("⏹️ المسح التلقائي متوقف.")
            if self.camera_thread and self.camera_thread.isRunning(): self.camera_thread.stop()
            self.camera_thread = None
        else:
            if self.camera_thread and self.camera_thread.isRunning(): self.camera_thread.stop(); self.camera_thread = None
            self.is_auto_scanning = True; self.pos_page.auto_scan_btn.setChecked(True); self.pos_page.auto_scan_status.setText("▶️ المسح التلقائي نشط..."); self.last_scanned_code = None
            self.start_camera_scan(continuous=True); self.pos_page.scan_btn.setEnabled(False)

    def handle_camera_error(self, msg):
        QMessageBox.critical(self, "خطأ كاميرا", msg)
        if self.is_auto_scanning:
            self.is_auto_scanning = False; self.pos_page.auto_scan_btn.setChecked(False); self.pos_page.auto_scan_status.setText("❌ خطأ في الكاميرا."); self.pos_page.scan_btn.setEnabled(True)

    def closeEvent(self, event):
        if self.camera_thread and self.camera_thread.isRunning(): self.camera_thread.stop()
        
        # Define a no-op close method to prevent errors on shutdown
        noop_close = lambda: None
        
        if self.kitchen_display:
            self.kitchen_display.close = noop_close
            QMainWindow.close(self.kitchen_display)

        if self.customer_display:
            self.customer_display.close = noop_close
            QMainWindow.close(self.customer_display)

        for f in os.listdir('.'):
            if (f.startswith('qr_') or f.startswith('invoice_qr_') or f.startswith('receipt_')) and (f.endswith('.png') or f.endswith('.pdf')):
                try: os.remove(f)
                except Exception as e: print(f"Could not remove temp file {f}: {e}")
        event.accept()

# ==============================================================================
# --- نقطة انطلاق البرنامج ---
# ==============================================================================
if __name__ == '__main__':
    # إنشاء المجلدات اللازمة إذا لم تكن موجودة
    if not os.path.exists('web/templates'):
        os.makedirs('web/templates')
    if not os.path.exists('web/static'):
        os.makedirs('web/static')

    # --- ملفات واجهة الويب (يتم إنشاؤها تلقائياً إذا لم تكن موجودة) ---
    html_file_path = 'web/templates/menu.html'
    if not os.path.exists(html_file_path):
        html_content = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>قائمة الطعام</title>
    <link rel="stylesheet" href="{{ url_for('static', filename='style.css') }}">
    <script src="https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js"></script>
</head>
<body>
    <header>
        <h1 id="restaurant-name">قائمة الطعام</h1>
        <div class="cart-button-container">
            <button id="cart-button">🛒 <span id="cart-count">0</span></button>
        </div>
    </header>
    <div id="categories" class="categories-container"></div>
    <main id="product-list" class="product-grid"></main>
    <div id="cart-modal" class="modal">
        <div class="modal-content">
            <span class="close-button">×</span>
            <h2>سلة الطلبات</h2>
            <div id="cart-items"></div>
            <p class="total">الإجمالي: <span id="cart-total">0.00</span></p>
            <hr>
            <div id="checkout-section">
                <button id="confirm-order-button">✅ تأكيد الطلب وإنشاء الرمز</button>
            </div>
            <div id="qr-code-section" style="display: none; text-align: center;">
                <h3>يرجى إظهار هذا الرمز للكاشير</h3>
                <div id="qrcode"></div>
                <p>امسح هذا الرمز عند الكاشير لإتمام طلبك.</p>
            </div>
        </div>
    </div>
    <div id="product-detail-modal" class="modal">
        <div class="modal-content">
            <span class="close-button" id="close-product-detail-modal">×</span>
            <h2 id="product-detail-name"></h2>
            <p id="product-detail-price" class="price"></p>
            <hr>
            <h3>الكمية:</h3>
            <div class="quantity-control">
                <button id="qty-minus-btn">-</button>
                <span id="qty-display">1</span>
                <button id="qty-plus-btn">+</button>
            </div>
            <hr>
            <h3>الإضافات:</h3>
            <div id="product-detail-modifiers" class="modifiers-list">
                <p class="no-modifiers">لا توجد إضافات متاحة لهذا المنتج.</p>
            </div>
            <button id="add-to-cart-from-detail" class="add-to-cart-button">أضف إلى السلة</button>
        </div>
    </div>
    <script src="{{ url_for('static', filename='app.js') }}"></script>
</body>
</html>
"""
        with open(html_file_path, 'w', encoding='utf-8') as f:
            f.write(html_content)

    css_file_path = 'web/static/style.css'
    if not os.path.exists(css_file_path):
        css_content = """
body{font-family:Tahoma,Arial,sans-serif;margin:0;background-color:#f4f4f4;color:#333}
header{background-color:#2c3e50;color:#fff;padding:1rem;text-align:center;position:sticky;top:0;z-index:1000;display:flex;justify-content:space-between;align-items:center}
header h1{margin:0;font-size:1.5rem}
.categories-container{display:flex;justify-content:center;flex-wrap:wrap;padding:10px;background:#ecf0f1;border-bottom:2px solid #bdc3c7}
.category-button{background-color:#3498db;color:#fff;border:none;padding:10px 20px;margin:5px;border-radius:20px;cursor:pointer;transition:background-color .3s}
.category-button.active,.category-button:hover{background-color:#2980b9}
.product-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:1.5rem;padding:1.5rem}
.product-card{background:#fff;border-radius:8px;box-shadow:0 4px 8px rgba(0,0,0,.1);overflow:hidden;display:flex;flex-direction:column; cursor: pointer;}
.product-card img{width:100%;height:180px;object-fit:cover;background-color:#eee}
.product-info{padding:1rem;flex-grow:1}
.product-info h3{margin:0 0 .5rem}
.product-info .price{font-size:1.2rem;font-weight:700;color:#27ae60}
.product-actions{padding:0 1rem 1rem}
.add-to-cart-button{background-color:#2ecc71;color:#fff;border:none;width:100%;padding:12px;border-radius:5px;font-size:1rem;font-weight:700;cursor:pointer;transition:background-color .2s}
.add-to-cart-button:hover{background-color:#27ae60}
.cart-button-container{position:relative}
#cart-button{background-color:#e67e22;color:#fff;border:none;padding:10px 15px;border-radius:50px;font-size:1.2rem;cursor:pointer}
#cart-count{background:#c0392b;border-radius:50%;padding:2px 7px;font-size:.8rem;position:absolute;top:-5px;right:-5px}
.modal{display:none;position:fixed;z-index:1001;left:0;top:0;width:100%;height:100%;overflow:auto;background-color:rgba(0,0,0,.5)}
.modal-content{background-color:#fefefe;margin:10% auto;padding:20px;border:1px solid #888;width:90%;max-width:500px;border-radius:10px;position:relative}
.close-button{color:#aaa;float:left;font-size:28px;font-weight:700}
.close-button:focus,.close-button:hover{color:#000;text-decoration:none;cursor:pointer}
#cart-items .cart-item{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid #eee}
#cart-items .cart-item:last-child{border-bottom:none}
.item-controls button{background:#e74c3c;color:#fff;border:none;border-radius:5px;width:25px;height:25px;cursor:pointer;margin:0 5px}
.item-controls .plus{background:#2ecc71}
#product-detail-modal .modal-content {max-width: 600px;}
#product-detail-modal h3 {margin-top: 15px;margin-bottom: 10px;font-size: 1.3rem;color: #34495e;}
.quantity-control {display: flex;justify-content: center;align-items: center;gap: 15px;margin-bottom: 15px;}
.quantity-control button {background-color: #3498db;color: white;border: none;border-radius: 5px;width: 45px;height: 45px;font-size: 1.8rem;font-weight: bold;cursor: pointer;transition: background-color 0.2s;}
.quantity-control button:hover {background-color: #2980b9;}
#qty-display {font-size: 2rem;font-weight: bold;color: #333;min-width: 50px;text-align: center;}
.modifiers-list {margin-bottom: 20px;padding: 10px;border: 1px solid #ddd;border-radius: 5px;background-color: #f9f9f9;}
.modifiers-list label {display: flex;align-items: center;margin-bottom: 8px;cursor: pointer;font-size: 1rem;color: #555;}
.modifiers-list input[type="checkbox"] {width: 20px;height: 20px;margin-left: 10px;cursor: pointer;flex-shrink: 0;}
.modifiers-list label:hover {color: #000;}
.modifiers-list .mod-price {font-weight: bold;color: #27ae60;margin-right: auto;margin-left: 0;}
.no-modifiers {text-align: center;color: #888;font-style: italic;padding: 10px;}
#add-to-cart-from-detail {width: 100%;}
"""
        with open(css_file_path, 'w', encoding='utf-8') as f:
            f.write(css_content)

    js_file_path = 'web/static/app.js'
    if not os.path.exists(js_file_path):
        js_content = """
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
    let currentProduct = null;

    async function fetchData() {
        try {
            const productsResponse = await fetch('/api/products');
            allProducts = await productsResponse.json();
            const configResponse = await fetch('/api/config');
            const config = await configResponse.json();
            currencySymbol = config.currency_symbol || 'ريال';
            restaurantNameH1.textContent = config.restaurant_name || 'قائمة الطعام';
            document.title = config.restaurant_name || 'قائمة الطعام';
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
            card.dataset.id = product.id;
            card.innerHTML = `
                <img src="/api/product_image/${product.id}" alt="${product.name}" onerror="this.style.backgroundColor='#eee'; this.src='';">
                <div class="product-info">
                    <h3>${product.name}</h3>
                    <p class="price">${product.price.toFixed(2)} ${currencySymbol}</p>
                </div>
                <div class="product-actions">
                    <button class="add-to-cart-button">أضف إلى السلة</button>
                </div>
            `;
            // Open detail modal when clicking anywhere on the card
            card.addEventListener('click', () => openProductDetail(product.id));
            productList.appendChild(card);
        });
    }

    function openProductDetail(productId) {
        currentProduct = allProducts.find(p => p.id === productId);
        if (!currentProduct) return;

        productDetailName.textContent = currentProduct.name;
        productDetailPrice.textContent = `${currentProduct.price.toFixed(2)} ${currencySymbol}`;
        qtyDisplay.textContent = '1';

        productDetailModifiers.innerHTML = '';
        if (currentProduct.modifiers && currentProduct.modifiers.length > 0) {
            currentProduct.modifiers.forEach(mod => {
                const label = document.createElement('label');
                label.innerHTML = `
                    <input type="checkbox" data-id="${mod.id}" data-price="${mod.price_change}"> 
                    <span>${mod.name}</span> 
                    <span class="mod-price">(+${mod.price_change.toFixed(2)} ${currencySymbol})</span>
                `;
                productDetailModifiers.appendChild(label);
            });
        } else {
            productDetailModifiers.innerHTML = '<p class="no-modifiers">لا توجد إضافات متاحة لهذا المنتج.</p>';
        }

        productDetailModal.style.display = 'block';
    }

    qtyPlusBtn.addEventListener('click', () => {
        let currentQty = parseInt(qtyDisplay.textContent);
        qtyDisplay.textContent = Math.min(99, currentQty + 1);
    });

    qtyMinusBtn.addEventListener('click', () => {
        let currentQty = parseInt(qtyDisplay.textContent);
        qtyDisplay.textContent = Math.max(1, currentQty - 1);
    });

    addToCartFromDetailButton.addEventListener('click', () => {
        if (!currentProduct) return;

        const quantity = parseInt(qtyDisplay.textContent);
        const selectedModifiers = [];
        productDetailModifiers.querySelectorAll('input[type="checkbox"]:checked').forEach(checkbox => {
            const modId = parseInt(checkbox.dataset.id);
            const modifier = currentProduct.modifiers.find(m => m.id === modId);
            if (modifier) {
                selectedModifiers.push({ id: modifier.id, name: modifier.name, price_change: modifier.price_change });
            }
        });

        const uniqueId = `${currentProduct.id}-${selectedModifiers.map(m => m.id).sort().join('-')}`;
        const existingCartItem = cart.find(item => item.uniqueId === uniqueId);

        if (existingCartItem) {
            existingCartItem.qty += quantity;
        } else {
            const modifiersTotal = selectedModifiers.reduce((sum, mod) => sum + mod.price_change, 0);
            const finalPricePerUnit = currentProduct.price + modifiersTotal;

            cart.push({
                uniqueId: uniqueId, id: currentProduct.id, name: currentProduct.name,
                price: finalPricePerUnit, qty: quantity, modifiers: selectedModifiers
            });
        }
        updateCart();
        productDetailModal.style.display = 'none';
    });
    
    closeProductDetailModalButton.addEventListener('click', () => productDetailModal.style.display = 'none');

    function updateCart() {
        cart = cart.filter(item => item.qty > 0);
        cartItemsContainer.innerHTML = '';
        let total = 0;
        let count = 0;

        cart.forEach(item => {
            const itemElement = document.createElement('div');
            itemElement.className = 'cart-item';
            
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
                <span>${(item.price * item.qty).toFixed(2)} ${currencySymbol}</span>`;
            cartItemsContainer.appendChild(itemElement);
            total += item.price * item.qty;
            count += item.qty;
        });

        cartTotalSpan.textContent = `${total.toFixed(2)} ${currencySymbol}`;
        cartCountSpan.textContent = count;
        
        document.querySelectorAll('.cart-item .plus').forEach(b => b.onclick = () => updateCartItemQuantity(b.dataset.id, 1));
        document.querySelectorAll('.cart-item .minus').forEach(b => b.onclick = () => updateCartItemQuantity(b.dataset.id, -1));
    }

    function updateCartItemQuantity(uniqueId, change) {
        const item = cart.find(i => i.uniqueId === uniqueId);
        if (item) { item.qty += change; updateCart(); }
    }

    confirmOrderButton.addEventListener('click', () => {
        if (cart.length === 0) { alert('سلتك فارغة!'); return; }
        const orderData = {
            source: 'WebApp',
            items: cart.map(item => ({ id: item.id, qty: item.qty, modifiers: item.modifiers ? item.modifiers.map(mod => mod.id) : [] }))
        };
        const jsonOrder = JSON.stringify(orderData);
        document.getElementById('checkout-section').style.display = 'none';
        document.getElementById('qr-code-section').style.display = 'block';
        qrCodeContainer.innerHTML = '';
        new QRCode(qrCodeContainer, { text: jsonOrder, width: 256, height: 256 });
    });

    cartButton.addEventListener('click', () => {
        document.getElementById('checkout-section').style.display = 'block';
        document.getElementById('qr-code-section').style.display = 'none';
        qrCodeContainer.innerHTML = '';
        cartModal.style.display = 'block';
    });
    closeModalButton.addEventListener('click', () => cartModal.style.display = 'none');
    window.addEventListener('click', (e) => {
        if (e.target == cartModal) cartModal.style.display = 'none'
        if (e.target == productDetailModal) productDetailModal.style.display = 'none';
    });
    
    fetchData();
});
"""
        with open(js_file_path, 'w', encoding='utf-8') as f:
            f.write(js_content)
    
    # التحقق من المكتبات المطلوبة وعرض تحذيرات
    if not ARABIC_SUPPORT: print("Warning: Arabic libraries not found. (pip install arabic_reshaper python-bidi)")
    if not ADVANCED_REPORTS_SUPPORT: print("Warning: Advanced reporting libraries not found. (pip install pandas matplotlib seaborn openpyxl)")
    if not PYZBAR_SUPPORT: print("Warning: pyzbar not found. QR code scanning might be less accurate. (pip install pyzbar)")
    if not WEB_SERVER_SUPPORT: print("Warning: Flask not found. Digital menu feature is disabled. (pip install Flask)")
    if not WINDOWS_PRINT_SUPPORT: print("Warning: Windows print support not found. Using basic printing method. (pip install pywin32)")
    else: print("✓ Windows print support enabled - Enhanced printing available")

    create_database_and_tables()
    add_sample_data_if_needed()
    
    app = QApplication(sys.argv)
    window = FoodTruckApp()
    
    window.showMaximized()
    
    # رسالة ترحيبية تعرض عنوان IP للخادم
    if WEB_SERVER_SUPPORT:
        ip_addr = get_local_ip()
        print("------------------------------------------------------------")
        print(">>> Digital Menu Server is RUNNING!")
        print(f">>> Access it from a phone on the same network at: http://{ip_addr}:5000")
        print(">>> You can create a QR code for auto-connect from the Settings page.")
        print("------------------------------------------------------------")

    sys.exit(app.exec())