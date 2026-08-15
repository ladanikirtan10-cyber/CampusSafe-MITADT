# CampusSafe — MIT ADT University Edition (V2)

This version adapts the CampusSafe prototype to the MIT ADT University campus context.

## Included
- MIT ADT campus-centered map
- MIT ADT facility/POI categories based on official public university information
- Student safety reporting
- Anonymous reporting
- Admin dashboard
- Risk scoring
- Black-spot clustering
- Red-time-zone analysis
- Safer-route recommendation
- Intervention workflow
- SQLite database
- SIMULATED demo incident generator

## Important data-quality note
This is an SIH/prototype build, not an authorized MIT ADT production system.

The MIT ADT Virtual Tour is an interactive 3D experience. Its page does not expose a complete machine-readable campus GIS/POI dataset through the normal web page, so this project does NOT claim to have extracted exact building geometry from the Virtual Tour.

POI coordinates in this V2 are reference approximations around the MIT ADT campus anchor. Before production use, replace them with an official MIT ADT GIS/GeoJSON/KML/CSV dataset or a campus-approved map.

Likewise, all incidents created by "Load Demo Data" are explicitly SIMULATED. Do not use them as evidence of real incidents.

## Run
From the project root:

```powershell
cd C:\Users\kirtan\Downloads\CampusSafe_Full_App
.\.venv\Scripts\Activate.ps1
cd .\campussafe_app
python app.py
```

Open:
- Student: http://127.0.0.1:5000/
- Admin: http://127.0.0.1:5000/admin

On the Admin page, "Load Demo Data" creates simulated incidents for demonstrating the analytics.

## Recommended next production step
Obtain from MIT ADT an authoritative:
- campus boundary
- building/hostel POIs
- internal road/path network
- security posts
- emergency/medical points
- approved incident categories
- data retention/access policy
- authorized integration/API details

Then import the approved GIS data and replace the simulated incident stream with authorized reports.
