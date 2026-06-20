# quick logic check — real M2 deltas
from src.eudr.cross_check import classify_plot

# (plot_id, ndvi_delta) from your M2 pivot
deltas = [
    ("KTP-001", -0.009),
    ("KTP-002", -0.006),
    ("KTP-003", -0.007),
    ("KTP-004",  0.010),
    ("KTP-005",  0.056),
    ("KTP-006", -0.066),
    ("KTP-007",  0.059),
    ("KTP-008", -0.117),
    ("KTP-009",  0.250),
    ("KTP-010",  0.244),
]

# we don't have real Hansen flags wired yet — test BOTH cases per plot
for plot_id, delta in deltas:
    no_loss  = classify_plot(hansen_flagged=False, ndvi_delta=delta)
    w_loss   = classify_plot(hansen_flagged=True,  ndvi_delta=delta)
    print(f"{plot_id}  Δ={delta:+.3f}   hansen=no → {no_loss:13}  hansen=yes → {w_loss}")