import pandas as pd
import os, pickle
import matplotlib.pyplot as plt
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.tree import DecisionTreeClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.metrics import accuracy_score
from ml_pipeline import CustomFeatures, TextCleaner

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, 'data', 'mail_data-1.csv')
MODEL_DIR = os.path.join(BASE_DIR, 'models')
if not os.path.exists(MODEL_DIR): os.makedirs(MODEL_DIR)

def main():
    print("📂 Đang đọc dữ liệu...")
    df = pd.read_csv(DATA_PATH, encoding='latin-1', on_bad_lines='skip')
    
    if len(df.columns) > 2:
        df = df.iloc[:, [0, 1]]
        
    df.columns = ['label', 'text']
    
    # Chuẩn hóa nhãn
    df['label'] = df['label'].str.strip().str.lower()
    df = df[df['label'].isin(['ham', 'spam'])]
    
    X = df['text'].values
    y = [1 if l == 'spam' else 0 for l in df['label']]
    
    print(f"📊 Đã tải {len(df)} dòng. Đang xử lý các đặc trưng thông qua Pipeline...")

    # Định nghĩa quy trình tiền xử lý
    text_pipe = Pipeline([
        ('cleaner', TextCleaner()),
        ('tfidf', TfidfVectorizer(stop_words='english', ngram_range=(1, 2), max_features=5000))
    ])
    
    # Gộp đặc trưng văn bản (TFIDF) và đặc trưng tùy chỉnh (độ dài, ký tự đặc biệt...)
    features = FeatureUnion([
        ('text_features', text_pipe),
        ('custom_features', CustomFeatures())
    ])

    # Train & Save
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    models = {
        'LR': LogisticRegression(max_iter=1000), 
        'RF': RandomForestClassifier(n_estimators=100), 
        'SVM': SVC(kernel='linear', probability=True), 
        'DT': DecisionTreeClassifier(), 
        'KNN': KNeighborsClassifier()
    }

    best_acc = 0
    best_model_name = ""

    model_names = []
    accuracies = []

    for code, clf in models.items():
        print(f"\n🚀 Đang huấn luyện mô hình {code}...")
        
        full_pipeline = Pipeline([
            ('features', features),
            ('classifier', clf)
        ])
        
        full_pipeline.fit(X_train, y_train)
        y_pred = full_pipeline.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        
        print(f"✅ Độ chính xác (Accuracy) của {code}: {acc:.4f}")
        model_names.append(code)
        accuracies.append(acc)
        
        if acc > best_acc:
            best_acc = acc
            best_model_name = code
            
        with open(os.path.join(MODEL_DIR, f'model_{code}.pkl'), 'wb') as f:
            pickle.dump(full_pipeline, f)
        print(f"💾 Đã lưu model_{code}.pkl (bao gồm cả pipeline)")

    print(f"\n✨ TẤT CẢ ĐÃ SẴN SÀNG! Thuật toán hiệu quả nhất trên tập test là: {best_model_name} (Acc: {best_acc:.4f})")

    # Hiển thị và lưu biểu đồ
    try:
        
        plt.figure(figsize=(10, 6))
        bars = plt.bar(model_names, [a * 100 for a in accuracies], color=['#FF9999', '#66B2FF', '#99FF99', '#FFCC99', '#FFD700'])
        
        plt.xlabel('Thuật toán Machine Learning', fontsize=12)
        plt.ylabel('Độ chính xác (%)', fontsize=12)
        plt.title('Biểu đồ so sánh độ chính xác phát hiện Spam', fontsize=14, fontweight='bold')
        plt.ylim(0, 110) # Tạo khoảng trống trên top để ghi số
        
        # Ghi số trực tiếp lên cột
        for bar in bars:
            yval = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2, yval + 1, f"{yval:.2f}%", ha='center', va='bottom', fontweight='bold')

        # Thư mục lưu biểu đồ
        static_dir = os.path.join(BASE_DIR, 'static', 'images')
        if not os.path.exists(static_dir):
            os.makedirs(static_dir)
            
        chart_path = os.path.join(static_dir, 'model_accuracy_chart.png')
        plt.savefig(chart_path)
        print(f"📈 Đã vẽ biểu đồ và lưu tại: {chart_path}")
        
        # Hiển thị trực tiếp lên màn hình
        print("Đang hiển thị biểu đồ, vui lòng đóng cửa sổ biểu đồ để hoàn tất...")
        plt.show()

    except ImportError:
        # print("\n💡 Gợi ý: Bạn có thể cài đặt thư viện để xem được biểu đồ trực quan bằng lệnh:")
        print(">>> pip install matplotlib")

if __name__ == '__main__': main()