This table contains new construction permit records from the City of Austin. Each record includes a free-text description field summarizing the scope of work. The goal is to analyze that description field and sort every record into one of five trade-specific tables based on the type of professional most likely to perform the work.

The five output tables should be: General Construction (new builds, additions, remodels, structural modifications — general contractors), Electrical (wiring, panels, solar installations, EV chargers — electricians), Plumbing (water heaters, gas lines, sewer, water supply — plumbers), Mechanical/HVAC (heating, cooling, ventilation, ductwork — HVAC technicians), and Site & Landscape (irrigation, fencing, grading, retaining walls, pools, tree removal — landscapers). Parse the description field using keyword matching or classification logic, assign each record to the single best-fit category, and export five separate CSV files into this repository. Flag any records that don't clearly fit a single category so they can be reviewed manually.

That should give Claude Code enough to work with while leaving room for it to make sensible parsing decisions on edge cases. If you want to adjust any of the five categories or shift where certain work types land, just say the word.


