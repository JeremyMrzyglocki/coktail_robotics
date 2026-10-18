# Compile eval — 2026-10-18 02:13 UTC

39 compiles (3 run(s) per prompt, set: all), 0 failed outright.

- **valid:** 34/39 (87%, 95% CI 73%–94%)
- **hands empty at the end:** 37/39 (95%, 95% CI 83%–99%)
- **grasp on the wrong kind of object:** 0
- **gaps with a candidate open dataset:** 31/31
- **median seconds:** 7.4

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 10.4s

Steps: locate_object(paint bucket) → grasp_object(paint bucket) → move_to_station(table) → locate_object(brush) → grasp_object(brush) → move_to_station(paint bucket) → move_to_station(table) → release_object(table) → move_to_station(table) → release_object(table)
- gap after step 6: `dip_brush_into_paint` — Dip the brush into the paint bucket to load it with paint. (data: epic-kitchens-100)
- gap after step 7: `drag_brush_along_surface` — Drag the brush along the table surface to draw an image. (data: epic-kitchens-100)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 7.1s

Steps: locate_object(paint bucket) → grasp_object(paint bucket) → move_to_station(table) → locate_object(brush) → grasp_object(brush) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 5: `dip_brush_into_vessel` — Dip the brush into the paint bucket to load paint onto it. (data: epic-kitchens-100)
- gap after step 5: `drag_brush_along_surface` — Drag the brush across the table surface to draw an image. (data: epic-kitchens-100)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 7.4s

Steps: locate_object(paint bucket) → grasp_object(paint bucket) → move_to_station(table) → locate_object(brush) → grasp_object(brush) → move_to_station(paint bucket) → move_to_station(table) → release_object(table) → move_to_station(table) → release_object(table)
- gap after step 6: `dip_item_into_container` — Dip the brush into the paint bucket to load paint onto the brush. (data: epic-kitchens-100)
- gap after step 7: `drag_item_along_surface` — Drag the brush along the table surface to draw the image. (data: epic-kitchens-100)

## build a small sandcastle on the tray with the bucket and shovel
**BLOCKED** · hands empty · 13.2s

Steps: locate_object(sand) → locate_object(bucket) → grasp_object(bucket) → move_to_station(tray) → release_object → locate_object(shovel) → grasp_object(shovel) → move_to_station(tray) → release_object
- gap after step 3: `scoop_substance` — Scoop sand or similar loose substance into a container. (data: epic-kitchens-100)
- gap after step 8: `shape_sand_with_shovel` — Use the shovel to shape sand on a surface. (data: epic-kitchens-100)
- ✗ unmet_precondition: Locate Object needs hand_empty (on the left hand), which no earlier step establishes.
- ✗ unmet_precondition: Grasp Object needs hand_empty (on the left hand), which no earlier step establishes.

## build a small sandcastle on the tray with the bucket and shovel
**BLOCKED** · hands empty · 12.3s

Steps: locate_object(sand) → locate_object(bucket) → grasp_object(bucket) → move_to_station(bucket) → release_object → locate_object(shovel) → grasp_object(shovel) → move_to_station(tray) → release_object → move_to_station(tray) → move_to_station(tray) → release_object
- gap after step 3: `scoop_substance` — Scoop sand or similar substance into a container. (data: jellyho-droid-subsets-scooping)
- gap after step 10: `shape_sandcastle` — Use a shovel to shape sand on a surface. (data: egocentric-10k)
- ✗ unmet_precondition: Release Object needs positioned (on the right hand), which no earlier step establishes.

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 8.8s

Steps: locate_object(sand) → locate_object(bucket) → grasp_object(bucket) → move_to_station(tray) → release_object → locate_object(shovel) → grasp_object(shovel) → move_to_station(tray) → release_object
- gap after step 3: `fill_container_with_substance` — Fill a container with a loose substance like sand. (data: epic-kitchens-100)
- gap after step 7: `shape_sand_with_tool` — Use a tool like a shovel to shape sand on a surface. (data: epic-kitchens-100)

## do a simple card trick with the deck on the table
valid · hands empty · 8.8s

Steps: locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(table) → locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(table)
- gap after step 2: `shake_item` — Shake a held item to randomize its contents. (data: egocentric-10k)
- gap after step 6: `drag_item_along_surface` — Drag a held item along a surface to reposition it. (data: egocentric-10k)

## do a simple card trick with the deck on the table
valid · hands empty · 13.3s

Steps: locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object → locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object → locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object
- gap after step 2: `shake_item` — Shake a held item to randomize its contents. (data: egocentric-10k)
- gap after step 6: `drag_item_along_surface` — Drag a held item along a surface to reposition it. (data: egocentric-10k)

## do a simple card trick with the deck on the table
valid · hands empty · 10.3s

Steps: locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(table) → locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(table) → locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(table)
- gap after step 2: `shake_object` — Shake the deck in hand to shuffle the cards. (data: egocentric-10k)
- gap after step 6: `drag_object_along_surface` — Drag the deck along the table surface. (data: egocentric-10k)
- gap after step 10: `drag_object_along_surface` — Drag the deck along the table surface. (data: egocentric-10k)

## water the two plants on the shelf
valid · hands empty · 8.2s

Steps: locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(plant1) → move_to_station(table) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(plant2) → move_to_station(table) → release_object
- gap after step 9: `tilt_out` — Tilt the held glass to pour water onto the plant. (data: droid)
- gap after step 14: `tilt_out` — Tilt the held glass to pour water onto the plant. (data: droid)

## water the two plants on the shelf
**BLOCKED** · hands empty · 19.2s

Steps: locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(plant1) → pour_into(plant1) → move_to_station(table) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(plant2) → pour_into(plant2) → move_to_station(table) → release_object
- ✗ wrong_flow: the glass is empty, so there is nothing to pour from it into the plant2. Things that hold something now: plant1. Hold the full vessel and pour into the plant2.

## water the two plants on the shelf
**BLOCKED** · hands empty · 16.4s

Steps: locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(plant1) → pour_into(plant1) → move_to_station(plant2) → pour_into(plant2) → move_to_station(table) → release_object
- ✗ wrong_flow: the glass is empty, so there is nothing to pour from it into the plant2. Things that hold something now: plant1. Hold the full vessel and pour into the plant2.

## write my name on the whiteboard with the marker
valid · hands empty · 4.8s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object(table)
- gap after step 3: `drag_along_surface` — Drag a held item along a fixed surface to write or draw. (data: epic-kitchens-100)

## write my name on the whiteboard with the marker
valid · hands empty · 4.6s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object(table)
- gap after step 3: `drag_along_surface` — Drag a held item along a fixed surface to write or draw. (data: epic-kitchens-100)

## write my name on the whiteboard with the marker
valid · hands empty · 7.1s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → release_object(whiteboard)

## make me a jam sandwich
valid · hands empty · 12.7s

Steps: locate_object(jam jar) → grasp_bottle(jam jar) → move_to_station(bread slice1) → pour_into(bread slice1) → move_to_station(table) → release_object → locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(table) → release_object → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object

## make me a jam sandwich
valid · **ends holding** · 11.9s

Steps: locate_object(jam jar) → grasp_bottle(jam jar) → move_to_station(bread slice1) → release_object → locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(table) → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object

## make me a jam sandwich
valid · hands empty · 14.4s

Steps: locate_object(bread slice1) → grasp_object(bread slice1) → move_to_station(table) → release_object(table) → locate_object(jam jar) → grasp_bottle(jam jar) → move_to_station(bread slice1) → pour_into(bread slice1) → move_to_station(table) → release_object(table) → locate_object(bread slice2) → grasp_object(bread slice2) → move_to_station(bread slice1) → release_object(bread slice1)

## put the flowers in the vase and add water
valid · hands empty · 5.6s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object(vase) → locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object(table)

## put the flowers in the vase and add water
valid · hands empty · 5.6s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object → locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object

## put the flowers in the vase and add water
valid · hands empty · 6.0s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object → locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 4.7s

Steps: locate_object(tin) → grasp_object(tin) → move_to_station(cat bowl) → pour_into(cat bowl) → move_to_station(table) → release_object(table)
- gap after step 2: `twist_item` — Twist an item held in hand to open or unscrew it. (data: jensenyuan-dextacwam-unscrew-bottle-cap)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 4.6s

Steps: locate_object(tin) → grasp_object(tin) → move_to_station(cat bowl) → pour_into(cat bowl) → move_to_station(table) → release_object(table)
- gap after step 2: `twist_item` — Twist an item held in hand to open or unscrew it. (data: jensenyuan-dextacwam-unscrew-bottle-cap)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 4.9s

Steps: locate_object(tin) → grasp_object(tin) → move_to_station(cat bowl) → pour_into(cat bowl) → move_to_station(table) → release_object
- gap after step 2: `twist_item` — Twist an item held in hand to open or unscrew it. (data: jensenyuan-dextacwam-unscrew-bottle-cap)

## make me a pina colada
valid · hands empty · 13.7s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(shaker) → grasp_shaker(shaker) → seal_shaker → shake_shaker(shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## make me a pina colada
valid · **ends holding** · 24.1s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(shaker) → grasp_shaker(shaker) → seal_shaker → shake_shaker → move_to_station(table) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(table) → locate_object(shaker) → grasp_shaker(shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## make me a pina colada
valid · hands empty · 14.4s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(shaker) → pour_into(shaker) → move_to_station(table) → release_object → locate_object(shaker) → grasp_shaker(shaker) → seal_shaker → shake_shaker(shaker) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## pour me a glass of juice
valid · hands empty · 4.2s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## pour me a glass of juice
valid · hands empty · 4.3s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(table)

## pour me a glass of juice
valid · hands empty · 3.9s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object

## mix me a smoothie
**BLOCKED** · hands empty · 20.1s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object → locate_object(strawberry) → grasp_object(strawberry) → move_to_station(blender jar) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(glass) → grasp_glass(glass) → move_to_station(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → release_object → move_to_station(table) → release_object
- gap after step 2: `peel_item` — Peel a fruit item to prepare it for blending. (data: epic-kitchens-100)
- gap after step 14: `press_button` — Press a control button on a fixed appliance. (data: epic-kitchens-100)
- ✗ unmet_precondition: Grasp Object needs object_located (on the right hand), which no earlier step establishes.
- ✗ unmet_precondition: Release Object needs positioned (on the right hand), which no earlier step establishes.

## mix me a smoothie
valid · hands empty · 22.8s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(table) → release_object → locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object → locate_object(strawberry) → grasp_object(strawberry) → move_to_station(blender jar) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object
- gap after step 3: `peel_item` — Peel the banana to prepare it for blending. (data: epic-kitchens-100)
- gap after step 18: `press_button` — Press the blender control button to start blending. (data: epic-kitchens-100)

## mix me a smoothie
valid · hands empty · 14.4s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object → locate_object(strawberry) → grasp_object(strawberry) → move_to_station(blender jar) → release_object → locate_object(milk) → grasp_bottle(milk) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → press_dispenser(blender) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 2: `peel_item` — Peel the banana to prepare it for blending. (data: epic-kitchens-100)

## wipe my table clean after dinner
valid · hands empty · 5.3s

Steps: locate_object(cloth) → grasp_cloth(cloth) → wipe_surface → move_to_station(table) → release_object

## wipe my table clean after dinner
valid · hands empty · 5.3s

Steps: locate_object(cloth) → grasp_cloth(cloth) → move_to_station(table) → wipe_surface → release_object

## wipe my table clean after dinner
valid · hands empty · 5.4s

Steps: locate_object(cloth) → grasp_cloth(cloth) → wipe_surface → move_to_station(table) → release_object

## clear the table and put the bottles away
valid · hands empty · 5.3s

Steps: locate_object(bottle1) → grasp_bottle(bottle1) → move_to_station(shelf) → release_object(shelf) → locate_object(bottle2) → grasp_bottle(bottle2) → move_to_station(shelf) → release_object(shelf)

## clear the table and put the bottles away
valid · hands empty · 4.8s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(shelf) → release_object → locate_object(orange juice) → grasp_bottle(orange juice) → move_to_station(shelf) → release_object

## clear the table and put the bottles away
valid · hands empty · 4.7s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(shelf) → release_object → locate_object(orange juice) → grasp_bottle(orange juice) → move_to_station(shelf) → release_object

