# Home top-up cards

Approved design: retain the existing hero, Top games, product-grid home-listing-grid, search and Buyer reviews. Insert six top-up discovery cards between Top games and Latest listings. Use the six supplied images without replacing existing game artwork.

1. Encode supplied images as WebP without upscaling or destructive cropping; publish new content-addressed objects to the existing public R2 bucket and record URLs, dimensions and hashes in data/home-topups.json.
2. Add a lightweight GET /api/top-up/home endpoint exposing only featured names, descriptions, artwork and existing catalogue routes. Validate selected slugs against the supplier catalogue. Steam uses the existing MYR wallet catalogue and labels its region.
3. Load the cards independently from listings and reviews, with a retry on failure and route-change protection. Scope responsive styling to the new section. Preserve all existing home sections and search geometry.
4. Verify metadata, routes, absence of supplier costs/secrets, delayed responses and recovery; run existing frontend and catalogue tests and desktop/mobile browser checks. Publish images only; website deployment is outside this change.
