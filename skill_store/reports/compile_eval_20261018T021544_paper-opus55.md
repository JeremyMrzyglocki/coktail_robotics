# Compile eval — 2026-10-18 02:15 UTC

39 compiles (3 run(s) per prompt, set: all), 0 failed outright.

- **valid:** 39/39 (100%, 95% CI 91%–100%)
- **hands empty at the end:** 39/39 (100%, 95% CI 91%–100%)
- **grasp on the wrong kind of object:** 0
- **gaps with a candidate open dataset:** 72/72
- **median seconds:** 24.2

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 18.6s

Steps: locate_object(paintbrush) → grasp_object(paintbrush) → move_to_station(paint bucket) → move_to_station(paint bucket) → move_to_station(table) → move_to_station(paint bucket) → release_object
- gap after step 3: `dip_into` — Press the held paintbrush down into the paint inside the bucket so the bristles take up paint. (data: epic-kitchens-100)
- gap after step 5: `drag_along_surface` — Drag the loaded paintbrush's bristles along the table to leave a painted stroke. (data: epic-kitchens-100)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 20.8s

Steps: locate_object(paint brush) → grasp_object(paint brush) → move_to_station(paint bucket) → move_to_station(paint bucket) → move_to_station(table) → move_to_station(paint bucket) → release_object
- gap after step 3: `dip_into` — Press the held paint brush down into the paint inside the paint bucket to load its bristles. (data: epic-kitchens-100)
- gap after step 5: `press_to_surface` — Lower the held paint brush until its bristles press onto the table. (data: droid)
- gap after step 5: `drag_along_surface` — Drag the held paint brush across the table to lay down a painted stroke. (data: epic-kitchens-100)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 19.6s

Steps: locate_object(paintbrush) → grasp_object(paintbrush) → move_to_station(paint bucket) → move_to_station(paint bucket) → move_to_station(table) → move_to_station(paint bucket) → release_object
- gap after step 3: `dip_into` — Press the held paintbrush down into the paint in the bucket so the bristles take up paint. (data: epic-kitchens-100)
- gap after step 5: `drag_along_surface` — Drag the held paintbrush's bristles along the table to lay down a paint stroke. (data: epic-kitchens-100)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 32.0s

Steps: locate_object(bucket) → grasp_object(bucket) → locate_object(shovel) → grasp_object(shovel) → move_to_station(bucket) → pour_into(bucket) → move_to_station(table) → release_object → move_to_station(tray) → move_to_station(table) → release_object
- gap after step 4: `scoop_material` — Push the held shovel into the sand on the tray and lift a load. (data: jellyho-droid-subsets-scooping)
- gap after step 6: `press_to_surface` — Press the held shovel down onto the sand inside the bucket to pack it. (data: epic-kitchens-100)
- gap after step 9: `invert_item` — Flip the held bucket upside down onto the tray. (data: egodex)
- gap after step 9: `press_to_surface` — Press the inverted bucket down onto the tray. (data: epic-kitchens-100)
- gap after step 9: `lift_off` — Lift the held bucket straight up off the sand tower. (data: droid)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 42.6s

Steps: locate_object(bucket) → grasp_object(bucket) → locate_object(shovel) → grasp_object(shovel) → move_to_station(sand box) → move_to_station(bucket) → pour_into(bucket) → move_to_station(table) → release_object → move_to_station(tray) → move_to_station(table) → release_object
- gap after step 5: `scoop_material` — Drag the held shovel through the sand in the sand box to load it. (data: epic-kitchens-100)
- gap after step 7: `press_to_surface` — Press the held shovel down onto the sand in the bucket to pack it. (data: epic-kitchens-100)
- gap after step 10: `invert_container` — Flip the held, sand-packed bucket upside down over the tray. (data: egodex)
- gap after step 10: `press_to_surface` — Press the inverted bucket down onto the tray. (data: epic-kitchens-100)
- gap after step 10: `lift_away` — Lift the inverted bucket straight up off the molded sand on the tray. (data: egodex)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 29.5s

Steps: locate_object(bucket) → grasp_object(bucket) → locate_object(shovel) → grasp_scoop(shovel) → move_to_station(sandbox) → move_to_station(bucket) → scoop_pour(bucket) → move_to_station(table) → release_object → move_to_station(tray) → move_to_station(tray) → move_to_station(table) → release_object
- gap after step 4: `press_into` — Push the held shovel blade down into the sand in the sandbox to load it. (data: jellyho-droid-subsets-scooping)
- gap after step 7: `press_to_surface` — Press the held shovel down onto the sand inside the bucket to pack it tight. (data: epic-kitchens-100)
- gap after step 10: `invert_item` — Turn the held bucket of packed sand upside down above the tray. (data: egodex)
- gap after step 10: `press_to_surface` — Press the inverted bucket down firmly onto the tray. (data: epic-kitchens-100)

## do a simple card trick with the deck on the table
valid · hands empty · 29.4s

Steps: locate_object(card deck) → grasp_object(card deck) → locate_object(chosen card) → grasp_object(chosen card) → move_to_station(card deck) → release_object → locate_object(card deck) → grasp_object(card deck) → move_to_station(card deck) → release_object → locate_object(chosen card) → grasp_object(chosen card) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 2: `fan_stack` — Slide the top cards of the card deck held in the other hand apart into a fan. (data: egodex)
- gap after step 4: `flip_item` — Turn the held chosen card face up toward the customer. (data: egodex)
- gap after step 4: `flip_item` — Turn the held chosen card back face down. (data: egodex)
- gap after step 4: `square_stack` — Push the fanned cards of the deck in the other hand together into a neat stack. (data: egodex)
- gap after step 10: `slide_off_stack` — Push cards one at a time off the deck held in the other hand. (data: egodex)
- gap after step 12: `flip_item` — Turn the held chosen card face up toward the customer. (data: egodex)

## do a simple card trick with the deck on the table
valid · hands empty · 39.6s

Steps: locate_object(deck of cards) → grasp_object(deck of cards) → locate_object(chosen card) → grasp_object(chosen card) → move_to_station(deck of cards) → release_object → move_to_station(table) → release_object
- gap after step 2: `fan_stack` — Drag the top cards along the held deck of cards to spread them into a fan. (data: egodex)
- gap after step 2: `square_stack` — Slide the fanned cards of the held deck back together into a squared deck. (data: egodex)
- gap after step 6: `cut_stack` — Lift the bottom half off the held deck of cards and press it onto the top half. (data: egodex)
- gap after step 8: `flip_item` — Turn the deck of cards on the table face up. (data: egodex)
- gap after step 8: `spread_on_surface` — Drag the deck of cards along the table to spread it out face up. (data: egodex)

## do a simple card trick with the deck on the table
valid · hands empty · 28.8s

Steps: locate_object(card deck) → grasp_object(card deck) → locate_object(chosen card) → grasp_object(chosen card) → move_to_station(card deck) → release_object → locate_object(card deck) → grasp_object(card deck) → move_to_station(card deck) → release_object → locate_object(chosen card) → grasp_object(chosen card) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 2: `fan_cards` — Drag the top cards of the held card deck across with the thumb into a fan. (data: egodex)
- gap after step 4: `flip_item` — Rotate the held chosen card face up toward the customer. (data: egodex)
- gap after step 4: `flip_item` — Rotate the held chosen card back face down. (data: egodex)
- gap after step 4: `press_to_square` — Press the fanned card deck in the left hand closed into a square stack. (data: egodex)
- gap after step 10: `deal_item` — Slide one card at a time off the card deck onto the table face up. (data: egodex)
- gap after step 12: `flip_item` — Rotate the held chosen card toward the customer. (data: egodex)

## water the two plants on the shelf
valid · hands empty · 13.0s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(plant1) → pour_into(plant1) → move_to_station(plant2) → pour_into(plant2) → move_to_station(table) → release_object

## water the two plants on the shelf
valid · hands empty · 14.5s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(plant1) → pour_into(plant1) → move_to_station(plant2) → pour_into(plant2) → move_to_station(table) → release_object

## water the two plants on the shelf
valid · hands empty · 13.8s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(plant1) → pour_into(plant1) → move_to_station(plant2) → pour_into(plant2) → move_to_station(table) → release_object

## write my name on the whiteboard with the marker
valid · hands empty · 26.6s

Steps: locate_object(marker) → grasp_object(marker) → locate_object(marker cap) → grasp_object(marker cap) → move_to_station(table) → release_object → move_to_station(whiteboard) → move_to_station(whiteboard) → move_to_station(marker cap) → locate_object(marker cap) → grasp_object(marker cap) → move_to_station(table) → release_object
- gap after step 4: `pull_apart` — Pull the marker cap axially off the marker held in the other hand. (data: egodex)
- gap after step 7: `press_to_surface` — Press the marker tip against the whiteboard with light contact force. (data: villekuosmanen-agilex-wipe-whiteboard)
- gap after step 7: `trace_path` — Drag the marker tip along the whiteboard following a letter's stroke path. (data: villekuosmanen-agilex-wipe-whiteboard)
- gap after step 11: `press_fit_onto` — Push the held marker cap onto the marker tip until it seats, then let go of it. (data: egodex)

## write my name on the whiteboard with the marker
valid · hands empty · 25.5s

Steps: locate_object(marker) → grasp_object(marker) → locate_object(marker cap) → grasp_object(marker cap) → move_to_station(table) → release_object → move_to_station(whiteboard) → locate_object(marker cap) → grasp_object(marker cap) → move_to_station(marker) → release_object → move_to_station(table) → release_object
- gap after step 4: `pull_off` — Pull the marker cap axially off the marker held in the other hand. (data: egodex)
- gap after step 7: `press_to_surface` — Press the held marker tip against the whiteboard surface. (data: villekuosmanen-agilex-wipe-whiteboard)
- gap after step 7: `drag_along_surface` — Drag the held marker tip along the whiteboard to draw a stroke. (data: villekuosmanen-agilex-wipe-whiteboard)
- gap after step 7: `lift_off_surface` — Lift the held marker tip away from the whiteboard. (data: villekuosmanen-agilex-wipe-whiteboard)
- gap after step 10: `press_fit_onto` — Press the held marker cap onto the marker until it seats. (data: villekuosmanen-agilex-cover-spary-lid)

## write my name on the whiteboard with the marker
valid · hands empty · 26.5s

Steps: locate_object(marker) → grasp_object(marker) → locate_object(marker cap) → grasp_object(marker cap) → move_to_station(table) → release_object → move_to_station(whiteboard) → move_to_station(marker cap) → locate_object(marker cap) → grasp_object(marker cap) → move_to_station(table) → release_object
- gap after step 4: `pull_off` — Pull the held marker cap straight off the marker body held in the other hand. (data: egodex)
- gap after step 7: `press_to_surface` — Press the held marker tip onto the whiteboard to start a stroke. (data: villekuosmanen-agilex-wipe-whiteboard)
- gap after step 7: `trace_stroke` — Drag the held marker along the whiteboard to trace one letter. (data: villekuosmanen-agilex-wipe-whiteboard)
- gap after step 7: `lift_from_surface` — Lift the held marker tip off the whiteboard between letters. (data: droid)
- gap after step 10: `press_fit_onto` — Press the held marker cap onto the marker held in the other hand and let go. (data: egodex)

## make me a jam sandwich
valid · hands empty · 27.9s

Steps: locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(plate) → release_object → locate_object(jam jar) → grasp_object(jam jar) → locate_object(butter knife) → grasp_object(butter knife) → move_to_station(jam jar) → move_to_station(bread slice1) → move_to_station(table) → release_object → move_to_station(table) → release_object → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object
- gap after step 9: `dip_into` — Lower the held butter knife into the jam jar to pick up jam. (data: epic-kitchens-100)
- gap after step 9: `withdraw_from` — Lift the jam-loaded butter knife back out of the jam jar. (data: epic-kitchens-100)
- gap after step 10: `spread_onto` — Drag the jam-loaded butter knife across bread slice1 to spread the jam. (data: epic-kitchens-100)

## make me a jam sandwich
valid · hands empty · 53.7s

Steps: locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(plate) → release_object → locate_object(jam jar) → grasp_object(jam jar) → locate_object(butter knife) → grasp_object(butter knife) → move_to_station(table) → release_object → move_to_station(bread slice1) → move_to_station(plate) → release_object → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object
- gap after step 6: `twist_open` — Twist the jam jar lid loose while the other hand holds the jam jar. (data: robocoin-airbot-mmk2-unscrew-bottle-cap)
- gap after step 8: `drag_through_substance` — Drag the held butter knife through the jam inside the open jam jar to load it. (data: epic-kitchens-100)
- gap after step 11: `spread_on_surface` — Drag the jam-loaded butter knife across bread slice1 to spread the jam. (data: epic-kitchens-100)
- gap after step 17: `press_to_surface` — Press down with the empty hand on bread slice2 so it sticks to bread slice1. (data: robocoin-airbot-mmk2-slide-block)

## make me a jam sandwich
valid · hands empty · 32.1s

Steps: locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(plate) → release_object → locate_object(jam jar) → grasp_object(jam jar) → move_to_station(table) → release_object → locate_object(butter knife) → grasp_object(butter knife) → move_to_station(table) → release_object → move_to_station(bread slice1) → move_to_station(plate) → release_object → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object
- gap after step 6: `twist_off_lid` — Grip the jam jar lid with the free hand and unscrew it from the jar held by the other hand. (data: robocoin-airbot-mmk2-unscrew-bottle-cap)
- gap after step 10: `scoop_with_blade` — Drag the held butter knife through the jam inside the jam jar to load its blade. (data: epic-kitchens-100)
- gap after step 13: `spread_onto_surface` — Drag the jam-loaded butter knife flat along bread slice1 to spread the jam. (data: epic-kitchens-100)
- gap after step 19: `press_to_surface` — Press the open hand down on bread slice2 so it sticks to bread slice1. (data: egodex)

## put the flowers in the vase and add water
valid · hands empty · 14.1s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object → locate_object(water jug) → grasp_bottle(water jug) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object

## put the flowers in the vase and add water
valid · hands empty · 14.3s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object → locate_object(water jug) → grasp_bottle(water jug) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object

## put the flowers in the vase and add water
valid · hands empty · 15.7s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object(flowers) → locate_object(water jug) → grasp_bottle(water jug) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object(water jug)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 24.2s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → locate_object(tin lid) → grasp_object(tin lid) → move_to_station(table) → release_object → locate_object(spoon) → grasp_object(spoon) → move_to_station(cat bowl) → pour_into(cat bowl) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 4: `peel_off` — Peel the pull-ring tin lid back and off the cat food tin held in the other hand. (data: epic-kitchens-100)
- gap after step 10: `scrape_out` — Drag the held spoon along the inside of the cat food tin to push the food into the cat bowl. (data: epic-kitchens-100)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 25.1s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → locate_object(tin lid) → move_to_station(table) → release_object → locate_object(feeding spoon) → grasp_object(feeding spoon) → move_to_station(cat bowl) → pour_into(cat bowl) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 3: `peel_off_lid` — Pull the ring-pull tin lid up and off the held cat food tin. (data: egodex)
- gap after step 9: `scrape_out` — Drag the held feeding spoon along the inside of the cat food tin to push the food into the cat bowl. (data: epic-kitchens-100)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 22.5s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → locate_object(tin lid) → grasp_object(tin lid) → move_to_station(table) → release_object → locate_object(fork) → grasp_object(fork) → move_to_station(cat bowl) → pour_into(cat bowl) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 4: `peel_off` — Peel the pull-ring tin lid back and off the cat food tin held in the other hand. (data: egodex)
- gap after step 10: `scrape_out` — Drag the held fork along the inside of the cat food tin to push the food into the cat bowl. (data: epic-kitchens-100)

## make me a pina colada
valid · hands empty · 26.2s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(cocktail shaker) → grasp_shaker(cocktail shaker) → seal_shaker(cocktail shaker) → shake_shaker(cocktail shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## make me a pina colada
valid · hands empty · 26.0s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(cocktail shaker) → grasp_shaker(cocktail shaker) → seal_shaker(cocktail shaker) → shake_shaker(cocktail shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## make me a pina colada
valid · hands empty · 27.6s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object → locate_object(cocktail shaker) → grasp_shaker(cocktail shaker) → seal_shaker(cocktail shaker) → shake_shaker(cocktail shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## pour me a glass of juice
valid · hands empty · 10.9s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## pour me a glass of juice
valid · hands empty · 8.4s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(table)

## pour me a glass of juice
valid · hands empty · 9.2s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## mix me a smoothie
valid · hands empty · 30.8s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(table) → release_object → move_to_station(blender jar) → release_object → locate_object(strawberry box) → grasp_object(strawberry box) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → run_blender(blender) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 2: `peel_item` — Grip the banana peel and pull it away from the banana held in the other hand. (data: epic-kitchens-100)

## mix me a smoothie
valid · hands empty · 51.9s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(table) → release_object → move_to_station(blender jar) → release_object → locate_object(strawberry box) → grasp_object(strawberry box) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → run_blender → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 2: `peel_item` — Pinch the banana stem and pull its peel down while the other hand holds the banana. (data: epic-kitchens-100)

## mix me a smoothie
valid · hands empty · 31.0s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object → move_to_station(table) → release_object → locate_object(strawberry box) → grasp_object(strawberry box) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → run_blender(blender) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 2: `peel_item` — Pinch the banana stem and drag the peel down strip by strip while the other hand holds the banana. (data: epic-kitchens-100)

## wipe my table clean after dinner
valid · hands empty · 9.7s

Steps: locate_object(cleaning cloth) → grasp_cloth(cleaning cloth) → wipe_surface(table) → move_to_station(table) → release_object

## wipe my table clean after dinner
valid · hands empty · 16.3s

Steps: locate_object(cleaning cloth) → grasp_cloth(cleaning cloth) → wipe_surface(table) → move_to_station(bin) → wipe_surface(table) → move_to_station(table) → release_object

## wipe my table clean after dinner
valid · hands empty · 9.8s

Steps: locate_object(cleaning cloth) → grasp_cloth(cleaning cloth) → wipe_surface(table) → move_to_station(table) → release_object

## clear the table and put the bottles away
valid · hands empty · 17.2s

Steps: locate_object(bottle1) → grasp_bottle(bottle1) → move_to_station(shelf) → release_object → locate_object(bottle2) → grasp_bottle(bottle2) → move_to_station(shelf) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(sink) → release_object → locate_object(coaster) → grasp_object(coaster) → move_to_station(shelf) → release_object

## clear the table and put the bottles away
valid · hands empty · 20.3s

Steps: locate_object(bottle1) → grasp_bottle(bottle1) → move_to_station(shelf) → release_object → locate_object(bottle2) → grasp_bottle(bottle2) → move_to_station(shelf) → release_object → locate_object(bottle3) → grasp_bottle(bottle3) → move_to_station(shelf) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(sink) → release_object → locate_object(coaster) → grasp_object(coaster) → move_to_station(shelf) → release_object

## clear the table and put the bottles away
valid · hands empty · 19.1s

Steps: locate_object(bottle1) → grasp_bottle(bottle1) → move_to_station(shelf) → release_object → locate_object(bottle2) → grasp_bottle(bottle2) → move_to_station(shelf) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(sink) → release_object → locate_object(coaster) → grasp_object(coaster) → move_to_station(shelf) → release_object

