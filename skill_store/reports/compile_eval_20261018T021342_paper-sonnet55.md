# Compile eval — 2026-10-18 02:13 UTC

39 compiles (3 run(s) per prompt, set: all), 0 failed outright.

- **valid:** 39/39 (100%, 95% CI 91%–100%)
- **hands empty at the end:** 39/39 (100%, 95% CI 91%–100%)
- **grasp on the wrong kind of object:** 0
- **gaps with a candidate open dataset:** 50/52
- **median seconds:** 9.2

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 9.8s

Steps: locate_object(brush) → grasp_object(brush) → move_to_station(paint bucket) → move_to_station(table) → release_object(table)
- gap after step 3: `dip_into_substance` — Lower the held brush into the paint in the bucket and lift it out loaded. (data: epic-kitchens-100)
- gap after step 4: `drag_tool_along_surface` — Drag the paint-loaded brush along the table surface to draw the image. (data: villekuosmanen-agilex-wipe-table-l2r)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 10.8s

Steps: locate_object(brush) → grasp_object(brush) → move_to_station(paint bucket) → move_to_station(table) → release_object(table)
- gap after step 3: `press_into_substance` — Press the brush tip down into the paint in the bucket to load it. (data: epic-kitchens-100)
- gap after step 4: `drag_along_surface` — Drag the loaded brush along the table in a curved stroke. (data: villekuosmanen-agilex-wipe-table-l2r)
- gap after step 4: `drag_along_surface` — Drag the loaded brush along the table in a straight stroke. (data: villekuosmanen-agilex-wipe-table-l2r)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 11.7s

Steps: locate_object(paintbrush) → grasp_object(paintbrush) → move_to_station(paint bucket) → move_to_station(table) → move_to_station(paint bucket) → move_to_station(table) → release_object(table)
- gap after step 3: `dip_into_vessel` — Lower the held paintbrush into the paint in the bucket and lift it out loaded. (data: epic-kitchens-100)
- gap after step 4: `drag_along_surface` — Drag the loaded paintbrush along the table in a stroke to lay down paint. (data: villekuosmanen-agilex-wipe-table-l2r)
- gap after step 5: `dip_into_vessel` — Lower the held paintbrush into the paint in the bucket and lift it out loaded. (data: epic-kitchens-100)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 41.0s

Steps: locate_object(shovel) → grasp_object(shovel) → locate_object(bucket) → grasp_object(bucket) → move_to_station(tray) → release_object → move_to_station(bucket) → pour_into(bucket) → move_to_station(tray) → release_object → locate_object(bucket) → grasp_object(bucket) → move_to_station(tray) → release_object
- gap after step 6: `push_into_substance` — Push the shovel blade into the sand to load it. (data: jellyho-droid-subsets-scooping)
- gap after step 8: `press_to_surface` — Press the sand down in the bucket with the shovel. (data: robocoin-airbot-mmk2-slide-block)
- gap after step 12: `flip_over` — Turn the held bucket upside down over the tray. (data: egodex)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 14.0s

Steps: locate_object(shovel) → grasp_object(shovel) → move_to_station(bucket) → pour_into(bucket) → move_to_station(table) → release_object(shovel) → locate_object(bucket) → grasp_object(bucket) → move_to_station(tray) → move_to_station(table) → release_object(bucket)
- gap after step 2: `scoop_substance` — Dig the held shovel into the sand and lift a load of sand. (data: jellyho-droid-subsets-scooping)
- gap after step 9: `flip_container` — Turn the held bucket upside down and set it on the tray to turn out the sand. (data: none)
- gap after step 9: `lift_off_surface` — Raise the inverted bucket straight up off the molded sand. (data: egodex)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 12.9s

Steps: locate_object(bucket) → grasp_object(bucket) → locate_object(shovel) → grasp_object(shovel) → move_to_station(bucket) → move_to_station(tray) → release_object → move_to_station(tray) → move_to_station(tray) → release_object
- gap after step 4: `drag_through_substance` — Drag the held shovel through the sand to load it. (data: jellyho-droid-subsets-scooping)
- gap after step 5: `tilt_out` — Tilt the loaded shovel to empty the sand into the bucket. (data: villekuosmanen-agilex-shovel-ice-into-cup)
- gap after step 5: `press_to_surface` — Press the shovel down onto the sand in the bucket to pack it. (data: villekuosmanen-agilex-press-socket-button)
- gap after step 8: `flip_over` — Flip the held bucket upside down onto the tray. (data: none)
- gap after step 8: `lift_off` — Lift the bucket straight up off the sand mound on the tray. (data: egodex)

## do a simple card trick with the deck on the table
valid · hands empty · 9.2s

Steps: locate_object(card deck) → grasp_object(card deck) → locate_object(top card) → grasp_object(top card) → move_to_station(card deck) → move_to_station(table) → release_object
- gap after step 4: `flip_item` — Turn the held top card over so its face shows to the audience. (data: egodex)
- gap after step 4: `flip_item` — Turn the held top card face down again to hide it. (data: egodex)
- gap after step 5: `press_to_surface` — Press the held top card into the middle of the card deck. (data: egodex)

## do a simple card trick with the deck on the table
valid · hands empty · 8.9s

Steps: locate_object(card deck) → grasp_object(card deck) → locate_object(top card) → grasp_object(top card) → move_to_station(card deck) → release_object(top card) → move_to_station(table) → release_object(card deck)
- gap after step 4: `flip_item` — Turn the held top card over so its face is shown to the audience. (data: egodex)
- gap after step 5: `press_onto_surface` — Press the held top card down onto the card deck so it is hidden in it. (data: robocoin-airbot-mmk2-slide-block)

## do a simple card trick with the deck on the table
valid · hands empty · 8.6s

Steps: locate_object(card deck) → grasp_object(card deck) → locate_object(top card) → grasp_object(top card) → move_to_station(table) → release_object
- gap after step 4: `flip_item` — Rotate the held top card face up so the audience can see it. (data: egodex)
- gap after step 4: `flip_item` — Rotate the held top card face down again before burying it. (data: egodex)
- gap after step 4: `slide_item_into` — Slide the held top card into the middle of the card deck. (data: egodex)

## water the two plants on the shelf
valid · hands empty · 7.5s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(plant1) → pour_into(plant1) → move_to_station(plant2) → pour_into(plant2) → move_to_station(table) → release_object

## water the two plants on the shelf
valid · hands empty · 7.8s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(plant1) → move_to_station(plant2) → move_to_station(table) → release_object
- gap after step 3: `tilt_out` — Tilt the held watering can over plant1 so water runs into its soil. (data: villekuosmanen-agilex-water-plant-1)
- gap after step 4: `tilt_out` — Tilt the held watering can over plant2 so water runs into its soil. (data: villekuosmanen-agilex-water-plant-4)

## water the two plants on the shelf
valid · hands empty · 7.3s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(plant1) → pour_into(plant1) → move_to_station(plant2) → pour_into(plant2) → move_to_station(shelf) → release_object

## write my name on the whiteboard with the marker
valid · hands empty · 7.9s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object
- gap after step 3: `drag_along_surface` — Drag the held marker tip along the whiteboard in the strokes of each letter of the name. (data: villekuosmanen-agilex-wipe-whiteboard)

## write my name on the whiteboard with the marker
valid · hands empty · 7.9s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object
- gap after step 2: `twist_open` — Twist the cap off the marker held in the right hand. (data: villekuosmanen-agilex-unscrew-cap)
- gap after step 3: `drag_tool_along_surface` — Drag the marker tip along the whiteboard in letter strokes; repeats until the whole name is written. (data: villekuosmanen-agilex-wipe-whiteboard)

## write my name on the whiteboard with the marker
valid · hands empty · 8.7s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object
- gap after step 2: `twist_off_cap` — Twist the cap off the marker held in the right hand so the tip is exposed. (data: villekuosmanen-agilex-unscrew-cap)
- gap after step 3: `drag_tool_along_surface` — Drag the marker tip along the whiteboard in letter strokes to write the customer's name. (data: villekuosmanen-agilex-wipe-whiteboard)

## make me a jam sandwich
valid · hands empty · 12.0s

Steps: locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(plate) → release_object(plate) → locate_object(butter knife) → grasp_object(butter knife) → move_to_station(jam jar) → move_to_station(bread slice1) → move_to_station(table) → release_object(table) → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object(bread slice1)
- gap after step 7: `press_into_substance` — Press the butter knife blade into the jam in the jar to load it. (data: epic-kitchens-100)
- gap after step 8: `drag_along_surface` — Drag the jam-loaded butter knife along bread slice1 to spread the jam. (data: epic-kitchens-100)

## make me a jam sandwich
valid · hands empty · 13.6s

Steps: locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(plate) → release_object → locate_object(jam jar) → grasp_object(jam jar) → locate_object(butter knife) → grasp_object(butter knife) → move_to_station(bread slice1) → move_to_station(table) → release_object → move_to_station(table) → release_object → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object
- gap after step 8: `dip_into_container` — Lower the held butter knife into the jam jar and lift out a load of jam. (data: epic-kitchens-100)
- gap after step 9: `drag_spread_on_surface` — Drag the held knife across bread slice1 to spread the jam evenly. (data: epic-kitchens-100)

## make me a jam sandwich
valid · hands empty · 10.9s

Steps: locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(plate) → release_object → locate_object(butter knife) → grasp_object(butter knife) → move_to_station(table) → release_object → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object
- gap after step 6: `dip_into_container` — Lower the held butter knife into the jam jar to pick up jam on its blade. (data: epic-kitchens-100)
- gap after step 6: `drag_along_surface` — Drag the jam-loaded butter knife across bread slice1 to spread the jam. (data: epic-kitchens-100)

## put the flowers in the vase and add water
valid · hands empty · 8.0s

Steps: locate_object(water jug) → grasp_bottle(water jug) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object → locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object

## put the flowers in the vase and add water
valid · hands empty · 10.7s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object(vase) → locate_object(water jug) → grasp_bottle(water jug) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object(table)

## put the flowers in the vase and add water
valid · hands empty · 8.7s

Steps: locate_object(water jug) → grasp_bottle(water jug) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object → locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 29.5s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → move_to_station(table) → release_object → locate_object(spoon) → grasp_object(spoon) → move_to_station(cat food tin) → move_to_station(cat bowl) → pour_into(cat bowl) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 2: `twist_off_lid` — Twist the tin lid off the cat food tin with the right hand while the left holds the tin. (data: robocoin-airbot-mmk2-unscrew-bottle-cap)
- gap after step 7: `scoop_substance` — Scoop cat food from the tin onto the spoon. (data: jellyho-droid-subsets-scooping)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 16.9s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → move_to_station(table) → release_object → move_to_station(cat bowl) → locate_object(spoon) → grasp_object(spoon) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 2: `pull_off_lid` — Pull the pull-tab lid up and back off the cat food tin with the right hand. (data: jensenyuan-dextacwam-unscrew-bottle-cap)
- gap after step 7: `scrape_out` — Scrape the cat food out of the tin into the cat bowl with the spoon. (data: epic-kitchens-100)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 10.2s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → move_to_station(table) → release_object → move_to_station(cat bowl) → pour_into(cat bowl) → locate_object(spoon) → grasp_object(spoon) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 2: `pull_open_lid` — Pull the tin lid open with the right hand while the left hand holds the cat food tin. (data: villekuosmanen-agilex-unscrew-cap)
- gap after step 8: `scrape_out` — Scrape the remaining cat food out of the tin into the cat bowl with the spoon. (data: epic-kitchens-100)

## make me a pina colada
valid · hands empty · 15.8s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object(table) → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object(table) → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(cocktail shaker) → pour_into(cocktail shaker) → move_to_station(table) → release_object(table) → locate_object(cocktail shaker) → grasp_shaker(cocktail shaker) → seal_shaker(cocktail shaker) → shake_shaker(cocktail shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(table)

## make me a pina colada
valid · hands empty · 17.3s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object(table) → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object(table) → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object(table) → locate_object(shaker) → grasp_shaker(shaker) → seal_shaker(shaker) → shake_shaker(shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(table)

## make me a pina colada
valid · hands empty · 21.4s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object(table) → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object(table) → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object(table) → locate_object(shaker) → grasp_shaker(shaker) → seal_shaker(shaker) → shake_shaker(shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(table)

## pour me a glass of juice
valid · hands empty · 5.9s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## pour me a glass of juice
valid · hands empty · 5.7s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## pour me a glass of juice
valid · hands empty · 6.0s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(table)

## mix me a smoothie
valid · hands empty · 24.0s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender) → release_object → locate_object(milk carton) → grasp_bottle(milk carton) → move_to_station(blender) → pour_into(blender) → move_to_station(table) → release_object → locate_object(blender lid) → grasp_object(blender lid) → move_to_station(blender) → release_object → run_blender(blender button) → move_to_station(table) → release_object → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object
- gap after step 2: `peel_item` — Strip the peel off the banana held in the left hand using the right hand. (data: egodex)
- gap after step 13: `press_onto_surface` — Press the blender lid down onto the blender rim until seated. (data: robocoin-airbot-mmk2-close-lid)
- gap after step 15: `lift_off_item` — Grip the blender lid and lift it off the blender. (data: egodex)
- gap after step 17: `grasp_fixed_container` — Grip and lift the blender jug, which no catalog grasp accepts. (data: unitreerobotics-g1-dex3-pickbottle-dataset)

## mix me a smoothie
valid · hands empty · 17.4s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → run_blender(blender button) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 2: `peel_item` — Peel the skin off the banana held in the left hand using the right hand. (data: egodex)

## mix me a smoothie
valid · hands empty · 12.1s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → run_blender(blender button) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 2: `peel_item` — Strip the peel off the banana held in the left hand using the right hand. (data: epic-kitchens-100)

## wipe my table clean after dinner
valid · hands empty · 6.2s

Steps: locate_object(cleaning cloth) → grasp_cloth(cleaning cloth) → wipe_surface(table) → move_to_station(table) → release_object

## wipe my table clean after dinner
valid · hands empty · 5.8s

Steps: locate_object(cloth) → grasp_cloth(cloth) → wipe_surface(table) → move_to_station(table) → release_object

## wipe my table clean after dinner
valid · hands empty · 6.1s

Steps: locate_object(dishcloth) → grasp_cloth(dishcloth) → wipe_surface(table) → move_to_station(table) → release_object

## clear the table and put the bottles away
valid · hands empty · 6.8s

Steps: locate_object(bottle1) → grasp_bottle(bottle1) → move_to_station(shelf) → release_object → locate_object(bottle2) → grasp_bottle(bottle2) → move_to_station(shelf) → release_object

## clear the table and put the bottles away
valid · hands empty · 6.8s

Steps: locate_object(bottle1) → grasp_bottle(bottle1) → move_to_station(shelf) → release_object → locate_object(bottle2) → grasp_bottle(bottle2) → move_to_station(shelf) → release_object

## clear the table and put the bottles away
valid · hands empty · 6.7s

Steps: locate_object(bottle1) → grasp_bottle(bottle1) → move_to_station(shelf) → release_object → locate_object(bottle2) → grasp_bottle(bottle2) → move_to_station(shelf) → release_object

