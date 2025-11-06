// DOM要素の取得
const getDataBtn = document.getElementById('getDataBtn');
const postDataBtn = document.getElementById('postDataBtn');
const resultArea = document.getElementById('result');

// データ取得ボタンのイベントリスナー
getDataBtn.addEventListener('click', async () => {
    try {
        const response = await fetch('/api/data');
        const data = await response.json();
        displayResult('データ取得成功', data);
    } catch (error) {
        displayResult('エラー', { error: error.message });
    }
});

// データ送信ボタンのイベントリスナー
postDataBtn.addEventListener('click', async () => {
    const testData = {
        message: 'テストデータ',
        timestamp: new Date().toISOString(),
        user: 'テストユーザー'
    };
    
    try {
        const response = await fetch('/api/data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(testData)
        });
        const data = await response.json();
        displayResult('データ送信成功', data);
    } catch (error) {
        displayResult('エラー', { error: error.message });
    }
});

// 結果を表示する関数
function displayResult(title, data) {
    resultArea.innerHTML = `
        <h3>${title}</h3>
        <pre>${JSON.stringify(data, null, 2)}</pre>
    `;
}

// ページ読み込み時の処理
document.addEventListener('DOMContentLoaded', () => {
    console.log('案件管理システムが読み込まれました');
});





