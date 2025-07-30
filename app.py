from flask import Flask, request, render_template, send_file
from werkzeug.utils import secure_filename
import os
from consolidation import load_data, greedy_consolidation, save_to_csv

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXT = {'xlsx'}
app.config.update(UPLOAD_FOLDER=UPLOAD_FOLDER, OUTPUT_FOLDER=OUTPUT_FOLDER)
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST':
        file = request.files['file']
        k = int(request.form['k_boxes'])
        thr = float(request.form.get('fill_thr', 0.7))
        allow_rot = 'allow_rot' in request.form

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            in_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(in_path)

            df = load_data(in_path)
            boxes = greedy_consolidation(df, k, fill_threshold=thr, allow_rot=allow_rot)

            out_name = f"boxes_{k}.csv"
            out_path = os.path.join(app.config['OUTPUT_FOLDER'], out_name)
            save_to_csv(boxes, out_path)
            return send_file(out_path, as_attachment=True)

    return render_template('index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
    