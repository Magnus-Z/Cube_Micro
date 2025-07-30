from flask import Flask, request, render_template_string, send_file, jsonify
from werkzeug.utils import secure_filename
import os
import pandas as pd
import itertools
import tempfile

app = Flask(__name__)
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'outputs'
ALLOWED_EXT = {'xlsx', 'csv'}
app.config.update(UPLOAD_FOLDER=UPLOAD_FOLDER, OUTPUT_FOLDER=OUTPUT_FOLDER)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Consolidation logic integrated
def load_data(path, sheet_name=None):
    """Load Excel or CSV file, read columns rlength, rwidth, rheight, compute volume."""
    try:
        if path.endswith('.csv'):
            df = pd.read_csv(path)
        elif path.endswith(('.xlsx', '.xls')):
            if sheet_name is None:
                df = pd.read_excel(path)
            else:
                df = pd.read_excel(path, sheet_name=sheet_name)
        else:
            raise ValueError("Unsupported file format. Use .xlsx, .xls, or .csv")
        
        required_columns = ["rlength", "rwidth", "rheight"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {missing_columns}")
        
        df = df[required_columns].dropna()
        df = df.astype({"rlength": float, "rwidth": float, "rheight": float})
        df["volume"] = df["rlength"] * df["rwidth"] * df["rheight"]
        return df
    except Exception as e:
        raise Exception(f"Error loading data: {str(e)}")

def exclude_largest(df):
    """Exclude the single row with maximum rlength."""
    idx = df["rlength"].idxmax()
    largest = df.loc[[idx]].copy()
    candidates = df.drop(idx).reset_index(drop=True)
    return largest, candidates

def fits_and_fill_rate(box_dims, items, allow_rotation=False):
    """Check if items fit into box_dims and compute minimum fill rate."""
    Lb, Wb, Hb = box_dims
    box_vol = Lb * Wb * Hb
    fill_rates = []
    for li, wi, hi in items:
        fits = False
        if allow_rotation:
            for perm in itertools.permutations((li, wi, hi)):
                if perm[0] <= Lb and perm[1] <= Wb and perm[2] <= Hb:
                    fits = True
                    break
        else:
            fits = (li <= Lb and wi <= Wb and hi <= Hb)
        if not fits:
            return False, 0.0
        fill_rates.append((li * wi * hi) / box_vol)
    return True, min(fill_rates)

def greedy_consolidation(df, target_k, fill_threshold=0.7, allow_rot=False):
    """Merge until total boxes (including largest) equals target_k."""
    largest, candidates = exclude_largest(df)
    clusters = [
        {"items": [i], "dims": (row.rlength, row.rwidth, row.rheight)}
        for i, row in candidates.iterrows()
    ]

    def volume(d): return d[0] * d[1] * d[2]

    while len(clusters) + 1 > target_k and len(clusters) > 1:
        best = None
        best_inc = float('inf')
        for i in range(len(clusters)):
            for j in range(i+1, len(clusters)):
                d1, d2 = clusters[i]['dims'], clusters[j]['dims']
                new_dims = tuple(max(a,b) for a,b in zip(d1, d2))
                items = [
                    candidates.loc[idx, ['rlength','rwidth','rheight']].tolist()
                    for idx in clusters[i]['items'] + clusters[j]['items']
                ]
                ok, fr = fits_and_fill_rate(new_dims, items, allow_rot)
                if ok and fr >= fill_threshold:
                    inc = volume(new_dims) - max(volume(d1), volume(d2))
                    if inc < best_inc:
                        best = (i, j, new_dims)
                        best_inc = inc
        if not best:
            break
        i,j,new_dims = best
        clusters[i]['dims'] = new_dims
        clusters[i]['items'] += clusters[j]['items']
        clusters.pop(j)

    final = []
    final.append({
        'box_id': 1,
        'rlength': float(largest.rlength.values[0]),
        'rwidth': float(largest.rwidth.values[0]),
        'rheight': float(largest.rheight.values[0])
    })
    for idx, c in enumerate(clusters, start=2):
        l,w,h = c['dims']
        final.append({'box_id': idx, 'rlength': l, 'rwidth': w, 'rheight': h})
    return final

def save_to_csv(boxes, output_path):
    df = pd.DataFrame(boxes)
    df.to_csv(output_path, index=False)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in ALLOWED_EXT

# HTML template embedded
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cube Micro - Box Consolidation Tool</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: 'Helvetica Neue', Arial, sans-serif;
      background: linear-gradient(135deg, #1570ef 0%, #0077d4 100%);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 15px;
      color: #2d3748;
    }
    .container {
      background: rgba(255, 255, 255, 0.98);
      backdrop-filter: blur(15px);
      border-radius: 16px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.15);
      padding: 30px;
      max-width: 700px;
      width: 100%;
      max-height: 95vh;
      overflow-y: auto;
    }
    .header {
      text-align: center;
      margin-bottom: 30px;
      padding-bottom: 25px;
      border-bottom: 1px solid #e2e8f0;
    }
    h1 {
      color: #2d3748;
      font-size: 2rem;
      font-weight: 300;
      margin: 10px 0;
    }
    .subtitle {
      color: #718096;
      font-size: 1rem;
      font-weight: 300;
    }
    .form-container {
      background: white;
      border-radius: 12px;
      padding: 25px;
      box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
    }
    .form-group {
      margin-bottom: 20px;
    }
    label {
      display: block;
      color: #2d3748;
      font-weight: 500;
      margin-bottom: 8px;
    }
    .required { color: #e53e3e; }
    input[type="file"], input[type="number"], input[type="text"] {
      width: 100%;
      padding: 14px 16px;
      border: 2px solid #e2e8f0;
      border-radius: 8px;
      font-size: 1rem;
      transition: all 0.3s ease;
      background: #fafafa;
    }
    input:focus {
      outline: none;
      border-color: #1570ef;
      background: white;
      box-shadow: 0 0 0 3px rgba(21, 112, 239, 0.1);
    }
    .checkbox-group {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px;
      background: #f8fafc;
      border-radius: 8px;
      border: 2px solid #e2e8f0;
    }
    .submit-btn {
      width: 100%;
      background: linear-gradient(135deg, #1570ef 0%, #0077d4 100%);
      color: white;
      border: none;
      padding: 16px 24px;
      border-radius: 8px;
      font-size: 1.1rem;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.3s ease;
      margin-top: 25px;
    }
    .submit-btn:hover {
      transform: translateY(-2px);
      box-shadow: 0 6px 25px rgba(21, 112, 239, 0.4);
    }
    .help-text {
      font-size: 0.875rem;
      color: #718096;
      margin-top: 6px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>📦 Cube Micro</h1>
      <div class="subtitle">Box Consolidation Tool</div>
    </div>

    <div class="form-container">
      <form method="post" enctype="multipart/form-data">
        <div class="form-group">
          <label for="file">Data File<span class="required">*</span></label>
          <input type="file" id="file" name="file" accept=".xlsx,.csv" required>
          <div class="help-text">Upload Excel (.xlsx) or CSV file with rlength, rwidth, rheight columns</div>
        </div>

        <div class="form-group">
          <label for="k_boxes">Target Number of Boxes<span class="required">*</span></label>
          <input type="number" id="k_boxes" name="k_boxes" min="1" required placeholder="e.g., 10">
        </div>

        <div class="form-group">
          <label for="fill_thr">Minimum Fill Rate</label>
          <input type="text" id="fill_thr" name="fill_thr" value="0.7" placeholder="0.7">
          <div class="help-text">Set fill efficiency (0.0 to 1.0)</div>
        </div>

        <div class="form-group">
          <div class="checkbox-group">
            <input type="checkbox" id="allow_rot" name="allow_rot">
            <label for="allow_rot">Allow item rotation during consolidation</label>
          </div>
        </div>

        <button type="submit" class="submit-btn">Run Consolidation Analysis</button>
      </form>
    </div>
  </div>
</body>
</html>
'''

@app.route('/', methods=['GET','POST'])
def index():
    if request.method == 'POST':
        try:
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
        except Exception as e:
            return f"<h2>Error:</h2><p>{str(e)}</p><a href='/'>Go Back</a>", 500

    return render_template_string(HTML_TEMPLATE)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
