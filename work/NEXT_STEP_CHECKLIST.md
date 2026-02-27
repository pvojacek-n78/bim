# Next step checklist (2D floorplan)

1. Verify layer mapping in work/floorplan_config.json matches your CAD standard.
2. Confirm slice/snap params and tune line_max_gap_m + line_min_density if walls are fragmented.
3. Run extraction script to produce raw/normalized DXF + wall lines DXF.
4. Validate QA report max deviation <= 0.02 m and check wall_segments_count > 0.
