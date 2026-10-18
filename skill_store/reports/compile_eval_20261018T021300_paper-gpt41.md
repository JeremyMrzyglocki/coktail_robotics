# Compile eval — 2026-10-18 02:13 UTC

39 compiles (3 run(s) per prompt, set: all), 1 failed outright.

- **valid:** 38/38 (100%, 95% CI 91%–100%)
- **hands empty at the end:** 38/38 (100%, 95% CI 91%–100%)
- **grasp on the wrong kind of object:** 0
- **gaps with a candidate open dataset:** 63/63
- **median seconds:** 6.6

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 5.2s

Steps: locate_object(paint brush) → grasp_object(paint brush) → move_to_station(paint bucket) → move_to_station(table) → move_to_station(table) → release_object(paint brush)
- gap after step 3: `dip_brush_in_liquid` — Dip the paint brush into the paint bucket to load it with paint. (data: ego-exo4d)
- gap after step 4: `drag_brush_on_surface` — Drag the paint brush along the table surface to draw an image. (data: ego-exo4d)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 5.1s

Steps: locate_object(paint brush) → grasp_object(paint brush) → move_to_station(paint bucket) → move_to_station(table) → move_to_station(table) → release_object(paint brush)
- gap after step 3: `dip_brush_in_liquid` — Dip the paint brush into the paint bucket to load it with paint. (data: ego-exo4d)
- gap after step 4: `drag_brush_on_surface` — Drag the paint brush along the table to draw an image. (data: ego-exo4d)

## You have a paint bucket and brush. draw an image on the table
valid · hands empty · 4.9s

Steps: locate_object(paint brush) → grasp_object(paint brush) → move_to_station(paint bucket) → move_to_station(table) → move_to_station(table) → release_object(table)
- gap after step 3: `dip_brush_in_liquid` — Dip the paint brush into the paint bucket to load it with paint. (data: ego-exo4d)
- gap after step 4: `drag_brush_on_surface` — Drag the paint brush along the table to draw an image. (data: ego-exo4d)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 6.9s

Steps: locate_object(shovel) → grasp_object(shovel) → locate_object(sand) → move_to_station(bucket) → locate_object(bucket) → grasp_object(bucket) → move_to_station(tray) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 3: `scoop_substance` — Scoop sand with the shovel from the sand pile. (data: epic-kitchens-100)
- gap after step 4: `tilt_out` — Tilt the shovel to pour sand into the bucket. (data: epic-kitchens-100)
- gap after step 7: `invert_item` — Invert the bucket onto the tray to form the sandcastle. (data: egodex)
- gap after step 7: `lift_off` — Lift the bucket off the sandcastle, leaving the sand behind. (data: egodex)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 7.7s

Steps: locate_object(shovel) → grasp_object(shovel) → locate_object(bucket) → grasp_object(bucket) → move_to_station(bucket) → move_to_station(bucket) → move_to_station(tray) → move_to_station(table) → release_object → move_to_station(table) → release_object
- gap after step 2: `scoop_with_shovel` — Use the shovel to scoop sand from the pile. (data: epic-kitchens-100)
- gap after step 5: `tilt_out_shovel` — Tilt the shovel to pour sand into the bucket. (data: epic-kitchens-100)
- gap after step 5: `scoop_with_shovel` — Use the shovel to scoop sand from the pile. (data: epic-kitchens-100)
- gap after step 6: `tilt_out_shovel` — Tilt the shovel to pour sand into the bucket. (data: epic-kitchens-100)
- gap after step 7: `invert_bucket` — Invert the bucket over the tray to shape the sandcastle. (data: egodex)
- gap after step 7: `lift_off_bucket` — Lift the bucket off the tray, leaving the sandcastle behind. (data: egodex)

## build a small sandcastle on the tray with the bucket and shovel
valid · hands empty · 16.2s

Steps: locate_object(shovel) → grasp_object(shovel) → locate_object(bucket) → grasp_object(bucket) → move_to_station(sand) → move_to_station(bucket) → move_to_station(table) → release_object → locate_object(shovel) → grasp_object(shovel) → move_to_station(sand) → move_to_station(bucket) → move_to_station(table) → release_object → move_to_station(tray) → move_to_station(table) → release_object
- gap after step 5: `scoop_with_tool` — Use the shovel to scoop sand from the pile. (data: epic-kitchens-100)
- gap after step 6: `tilt_out` — Tilt the shovel to pour sand into the bucket. (data: epic-kitchens-100)
- gap after step 11: `scoop_with_tool` — Use the shovel to scoop sand from the pile. (data: epic-kitchens-100)
- gap after step 12: `tilt_out` — Tilt the shovel to pour sand into the bucket. (data: epic-kitchens-100)
- gap after step 15: `invert_vessel_on_surface` — Invert the bucket onto the tray to form the sandcastle shape. (data: egodex)
- gap after step 15: `lift_vessel_off_cast` — Lift the bucket off the sandcastle to reveal the shape. (data: egodex)

## do a simple card trick with the deck on the table
valid · hands empty · 3.1s

Steps: locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(deck)

## do a simple card trick with the deck on the table
valid · hands empty · 2.6s

Steps: locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(deck)

## do a simple card trick with the deck on the table
valid · hands empty · 3.2s

Steps: locate_object(deck) → grasp_object(deck) → move_to_station(table) → release_object(deck)

## water the two plants on the shelf
valid · hands empty · 6.9s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(sink) → move_to_station(plant1) → move_to_station(plant2) → move_to_station(table) → release_object
- gap after step 3: `fill_vessel_from_tap` — Fill the watering can with water from the sink. (data: epic-kitchens-100)
- gap after step 4: `pour_from_item_to_item` — Pour water from the watering can into plant1. (data: epic-kitchens-100)
- gap after step 5: `pour_from_item_to_item` — Pour water from the watering can into plant2. (data: epic-kitchens-100)

## water the two plants on the shelf
valid · hands empty · 7.0s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(sink) → move_to_station(plant1) → pour_into(plant1) → move_to_station(plant2) → pour_into(plant2) → move_to_station(table) → release_object(watering can)
- gap after step 3: `fill_item_from_sink` — Fill the watering can with water from the sink. (data: epic-kitchens-100)

## water the two plants on the shelf
valid · hands empty · 7.5s

Steps: locate_object(watering can) → grasp_object(watering can) → move_to_station(sink) → move_to_station(plant1) → move_to_station(plant2) → move_to_station(table) → release_object(table)
- gap after step 3: `fill_vessel` — Fill the watering can with water at the sink. (data: epic-kitchens-100)
- gap after step 4: `tilt_out` — Tilt the watering can to pour water into plant1. (data: epic-kitchens-100)
- gap after step 5: `tilt_out` — Tilt the watering can to pour water into plant2. (data: epic-kitchens-100)

## write my name on the whiteboard with the marker
valid · hands empty · 4.3s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object(marker)
- gap after step 3: `press_to_surface` — Press the marker tip against the whiteboard to begin writing. (data: egocentric-10k)
- gap after step 3: `drag_on_surface` — Drag the marker tip along the whiteboard to form letters. (data: egocentric-10k)

## write my name on the whiteboard with the marker
valid · hands empty · 3.8s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object(marker)
- gap after step 3: `press_to_surface` — Press the marker tip against the whiteboard to begin writing. (data: egodex)
- gap after step 3: `drag_on_surface` — Drag the marker tip along the whiteboard to form letters. (data: egodex)

## write my name on the whiteboard with the marker
valid · hands empty · 3.9s

Steps: locate_object(marker) → grasp_object(marker) → move_to_station(whiteboard) → move_to_station(table) → release_object(marker)
- gap after step 3: `press_to_surface` — Press the marker tip against the whiteboard to begin writing. (data: egocentric-10k)
- gap after step 3: `drag_on_surface` — Drag the marker tip along the whiteboard to form letters. (data: egocentric-10k)

## make me a jam sandwich
valid · hands empty · 6.9s

Steps: locate_object(jam) → grasp_object(jam) → locate_object(knife) → grasp_object(knife) → move_to_station(jam) → move_to_station(bread1) → move_to_station(table) → release_object(knife) → move_to_station(table) → release_object(jam) → locate_object(bread2) → grasp_object(bread2) → move_to_station(bread1) → release_object(bread2)
- gap after step 2: `twist_open_item` — Twist open the jam jar held in the left hand. (data: jensenyuan-dextacwam-unscrew-bottle-cap)
- gap after step 5: `scoop_item_with_tool` — Scoop jam from the jar using the knife held in the right hand. (data: epic-kitchens-100)
- gap after step 6: `spread_item_with_tool` — Spread jam onto bread1 using the knife held in the right hand. (data: epic-kitchens-100)

## make me a jam sandwich
valid · hands empty · 7.3s

Steps: locate_object(jam) → grasp_object(jam) → locate_object(knife) → grasp_object(knife) → move_to_station(jam) → move_to_station(bread1) → move_to_station(table) → release_object(table) → locate_object(bread2) → grasp_object(bread2) → move_to_station(bread1) → release_object(bread1) → move_to_station(table) → release_object(table)
- gap after step 2: `twist_open_item` — Twist open the jam jar to remove its lid. (data: jensenyuan-dextacwam-unscrew-bottle-cap)
- gap after step 5: `scoop_item` — Scoop jam from the open jar using the knife. (data: epic-kitchens-100)
- gap after step 6: `spread_item_on_surface` — Spread jam from the knife onto the surface of bread1. (data: epic-kitchens-100)

## make me a jam sandwich
valid · hands empty · 7.0s

Steps: locate_object(jam) → grasp_object(jam) → locate_object(knife) → grasp_object(knife) → move_to_station(jam) → move_to_station(bread1) → move_to_station(table) → release_object → locate_object(bread2) → grasp_object(bread2) → move_to_station(bread1) → release_object → move_to_station(table) → release_object
- gap after step 2: `twist_open_item` — Twist open the jam jar held in the left hand. (data: jensenyuan-dextacwam-unscrew-bottle-cap)
- gap after step 5: `scoop_item_with_tool` — Scoop jam from the jar using the knife held in the right hand. (data: epic-kitchens-100)
- gap after step 6: `spread_item_with_tool` — Spread jam onto bread1 using the knife held in the right hand. (data: epic-kitchens-100)

## put the flowers in the vase and add water
valid · hands empty · 6.9s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object(vase) → locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object(table)

## put the flowers in the vase and add water
valid · hands empty · 6.6s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object → locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object

## put the flowers in the vase and add water
valid · hands empty · 8.7s

Steps: locate_object(flowers) → grasp_object(flowers) → move_to_station(vase) → release_object → locate_object(water bottle) → grasp_bottle(water bottle) → move_to_station(vase) → pour_into(vase) → move_to_station(table) → release_object

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 5.0s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → locate_object(tin lid) → grasp_object(tin lid) → move_to_station(table) → release_object → move_to_station(cat bowl) → move_to_station(table) → release_object
- gap after step 4: `lift_off_lid` — Lift the tin lid off the cat food tin while holding both. (data: ego-exo4d)
- gap after step 7: `tilt_out_food` — Tilt the cat food tin to pour the food into the cat bowl. (data: ego-exo4d)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 5.5s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → locate_object(tin lid) → grasp_object(tin lid) → move_to_station(table) → release_object(tin lid) → move_to_station(cat bowl) → move_to_station(table) → release_object(cat food tin)
- gap after step 4: `twist_open` — Twist the tin lid to break the seal and open the cat food tin. (data: jensenyuan-dextacwam-unscrew-bottle-cap)
- gap after step 4: `lift_off` — Lift the loosened tin lid off the cat food tin. (data: egodex)
- gap after step 7: `tilt_out` — Tilt the cat food tin to pour the food into the cat bowl. (data: droid)

## feed the cat: open the tin and put the food in her bowl
valid · hands empty · 5.0s

Steps: locate_object(cat food tin) → grasp_object(cat food tin) → locate_object(tin lid) → move_to_station(table) → release_object → move_to_station(cat bowl) → move_to_station(table) → release_object
- gap after step 3: `twist_open` — Twist the tin lid to break the seal and open the cat food tin. (data: jensenyuan-dextacwam-unscrew-bottle-cap)
- gap after step 3: `lift_off` — Lift the loosened tin lid off the cat food tin. (data: egodex)
- gap after step 6: `tilt_out` — Tilt the cat food tin to pour the food into the cat bowl. (data: droid)

## make me a pina colada
valid · hands empty · 7.5s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 18: `press_to_surface` — Press the blender button to start blending. (data: epic-kitchens-100)

## make me a pina colada
valid · hands empty · 12.3s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → run_blender(blender) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object
- gap after step 18: `place_item_on_appliance` — Place the blender jar onto the blender base for blending. (data: egodex)
- gap after step 24: `place_item_on_appliance` — Place the blender jar back onto the blender base after pouring. (data: egodex)

## make me a pina colada
valid · hands empty · 8.4s

Steps: locate_object(white rum) → grasp_bottle(white rum) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(pineapple juice) → grasp_bottle(pineapple juice) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → locate_object(coconut cream) → grasp_bottle(coconut cream) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object → run_blender(blender) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → move_to_station(blender) → release_object
- gap after step 18: `press_to_surface` — Press the blender jar down onto the blender base to prepare for blending. (data: egodex)
- gap after step 22: `tilt_out` — Tilt the blender jar to pour its contents into the glass. (data: droid)

## pour me a glass of juice
valid · hands empty · 3.0s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(juice)

## pour me a glass of juice
valid · hands empty · 3.0s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(juice)

## pour me a glass of juice
valid · hands empty · 3.1s

Steps: locate_object(juice) → grasp_bottle(juice) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(juice)

## mix me a smoothie
valid · hands empty · 6.3s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object(blender jar) → locate_object(orange juice) → grasp_bottle(orange juice) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object(table) → run_blender(blender) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object(blender)
- gap after step 2: `peel_item` — Peel the banana using the right hand while holding it with the left. (data: epic-kitchens-100)

## mix me a smoothie
valid · hands empty · 6.4s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object(blender jar) → locate_object(orange juice) → grasp_bottle(orange juice) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object(table) → run_blender(blender) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(table) → release_object(table)
- gap after step 2: `peel_item` — Peel the banana using the right hand while holding it with the left. (data: epic-kitchens-100)

## mix me a smoothie
valid · hands empty · 15.3s

Steps: locate_object(banana) → grasp_object(banana) → move_to_station(blender jar) → release_object(blender jar) → locate_object(orange juice) → grasp_bottle(orange juice) → move_to_station(blender jar) → pour_into(blender jar) → move_to_station(table) → release_object(table) → run_blender(blender) → locate_object(glass) → grasp_glass(glass) → locate_object(blender jar) → grasp_object(blender jar) → move_to_station(glass) → pour_into(glass) → move_to_station(blender) → release_object(blender) → move_to_station(table) → release_object(table)
- gap after step 2: `peel_item` — Peel the banana using the left hand. (data: epic-kitchens-100)

## wipe my table clean after dinner
valid · hands empty · 3.6s

Steps: locate_object(cloth) → grasp_cloth(cloth) → wipe_surface(table) → move_to_station(bin) → move_to_station(table) → release_object(table)
- gap after step 4: `shake_out` — Shake the cloth over the bin to remove crumbs. (data: ego-exo4d)

## wipe my table clean after dinner
valid · hands empty · 6.8s

Steps: locate_object(cloth) → grasp_cloth(cloth) → wipe_surface(table) → move_to_station(bin) → move_to_station(table) → release_object(table)
- gap after step 4: `shake_out` — Shake crumbs from the cloth into the bin. (data: ego-exo4d)

## wipe my table clean after dinner
valid · hands empty · 3.8s

Steps: locate_object(cloth) → grasp_cloth(cloth) → wipe_surface(table) → move_to_station(bin) → move_to_station(table) → release_object(table)
- gap after step 4: `shake_out` — Shake the cloth over the bin to remove crumbs. (data: ego-exo4d)

## clear the table and put the bottles away
valid · hands empty · 15.0s

Steps: locate_object(glass) → grasp_glass(glass) → move_to_station(bottle shelf) → release_object(bottle shelf) → locate_object(coaster) → grasp_object(coaster) → move_to_station(bottle shelf) → release_object(bottle shelf) → locate_object(banana) → grasp_object(banana) → move_to_station(bottle shelf) → release_object(bottle shelf) → locate_object(juice) → grasp_bottle(juice) → move_to_station(bottle shelf) → return_to_shelf(juice) → locate_object(white rum) → grasp_bottle(white rum) → move_to_station(bottle shelf) → return_to_shelf(white rum)

## clear the table and put the bottles away
FAILED: OpenAI rate limit or no credit on this key

## clear the table and put the bottles away
valid · hands empty · 15.7s

Steps: locate_object(glass) → grasp_glass(glass) → move_to_station(table) → release_object → locate_object(coaster) → grasp_object(coaster) → move_to_station(table) → release_object → locate_object(banana) → grasp_object(banana) → move_to_station(table) → release_object → locate_object(juice) → grasp_bottle(juice) → move_to_station(bottle shelf) → return_to_shelf → locate_object(white rum) → grasp_bottle(white rum) → move_to_station(bottle shelf) → return_to_shelf

