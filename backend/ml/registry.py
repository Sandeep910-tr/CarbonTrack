"""Model Registry (Priority 1 #8).

register_version() is called once per model right after training in
ml/pipeline.py and ml/train.py. It:
  1. Copies the just-trained {model_name}.pkl into ml/saved/versions/
     as {model_name}_v{N}.pkl (an immutable, numbered snapshot).
  2. Records a ModelVersion row with the metric, dataset size, and
     timestamp for that version.
  3. Compares the new metric against the currently *active* version's
     metric. Only activates the new version (leaves the just-trained file
     in place as the live {model_name}.pkl that ml/predict.py loads) if
     it's actually better. If it's worse, the previous active version's
     file is restored over {model_name}.pkl - a bad retrain never
     silently replaces a good model just because it ran more recently.

rollback_to() lets an admin explicitly reactivate any past version on
demand (routes/admin.py: POST /ml/models/<name>/rollback/<version_id>).
"""
import os
import json
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(BASE, "saved")
VERSIONS_DIR = os.path.join(SAVE, "versions")

METRIC_DIRECTION = {
    # model_name -> (metric_key in the training metrics dict, higher_is_better)
    "fuel_model": ("fuel_mae_l", False),
    "co2_model": ("co2_mae_kg", False),
    "eco_score_model": ("eco_score_mae", False),
    "maintenance_model": ("maintenance_accuracy", True),
    "route_model": ("route_accuracy", True),
}


def register_version(model_name, metrics, dataset_rows):
    """Call right after joblib.dump(...) has written the freshly trained
    model to ml/saved/{model_name}.pkl. Returns the ModelVersion row
    (already committed) describing what happened."""
    from models.db import db, ModelVersion

    os.makedirs(VERSIONS_DIR, exist_ok=True)
    metric_key, higher_is_better = METRIC_DIRECTION.get(model_name, (None, False))
    metric_value = metrics.get(metric_key) if metric_key else None

    active = ModelVersion.query.filter_by(model_name=model_name, is_active=True).first()
    last_version = (ModelVersion.query.filter_by(model_name=model_name)
                     .order_by(ModelVersion.version.desc()).first())
    new_version_num = (last_version.version + 1) if last_version else 1

    src = os.path.join(SAVE, f"{model_name}.pkl")
    versioned_path = os.path.join(VERSIONS_DIR, f"{model_name}_v{new_version_num}.pkl")
    shutil.copy2(src, versioned_path)

    is_better = True
    if active is not None and active.metric_value is not None and metric_value is not None:
        is_better = (metric_value > active.metric_value) if higher_is_better else (metric_value < active.metric_value)

    row = ModelVersion(
        model_name=model_name, version=new_version_num, metric_name=metric_key,
        metric_value=metric_value, higher_is_better=higher_is_better,
        metrics_json=json.dumps(metrics), dataset_rows=dataset_rows,
        file_path=versioned_path, is_active=False,
    )
    db.session.add(row)

    if is_better or active is None:
        if active is not None:
            active.is_active = False
        row.is_active = True
        # `src` (the live {model_name}.pkl) is already the just-trained
        # model, so it's already correct - nothing else to copy.
    else:
        # Worse than what's live: restore the previously active version's
        # file over the live path so this retrain doesn't regress anything,
        # even though its own snapshot is still kept in the registry.
        if active.file_path and os.path.exists(active.file_path):
            shutil.copy2(active.file_path, src)

    db.session.commit()
    return row, is_better or active is None


def rollback_to(version_id):
    """Reactivates a specific past version: copies its snapshot back over
    the live {model_name}.pkl, flips is_active flags, and clears
    ml/predict.py's model cache so the change takes effect on the very next
    prediction request."""
    from models.db import db, ModelVersion

    target = db.get_or_404(ModelVersion, version_id)
    if not os.path.exists(target.file_path):
        raise FileNotFoundError(f"Snapshot file missing for {target.model_name} v{target.version}: {target.file_path}")

    live_path = os.path.join(SAVE, f"{target.model_name}.pkl")
    shutil.copy2(target.file_path, live_path)

    ModelVersion.query.filter_by(model_name=target.model_name, is_active=True).update({"is_active": False})
    target.is_active = True
    db.session.commit()

    from ml import predict as predict_module
    predict_module._cache.clear()
    return target
