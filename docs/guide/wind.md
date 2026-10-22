# Wind

Wind is Swayfield's headline feature. It is procedural and driven by scene time, so there is nothing to simulate or bake. Press play and it moves.

## How the wind field works

Every frame, each blade asks the wind field "which way and how hard am I being pushed?" The answer is made of stacked parts:

1. **Base lean**: a constant push along the wind direction. How bent the grass is between gusts.
2. **Gusts**: a slow noise pattern, stretched along the wind direction and scrolled across the field. This makes the long bright streaks.
3. **Waves** (optional): regular rolling rows along the wind.
4. **Flutter**: fast, small shaking that mostly moves the tips. Wisps flutter more.
5. **Effectors**: local forces from objects such as a vortex or a trample. See [Effectors](effectors.md).

The blade then bends by rotating around its root, so it never gets shorter. The bend is stiff near the root and loose near the tip (**Stiffness**), and tips lag slightly behind the root in time (**Tip Lag**), like real stems.

The `sf_wind` attribute stores how far a blade is flattened beyond the steady lean: 0 means resting at the steady lean, 1 means fully flattened by a gust or effector. The material uses it to brighten flattened grass, so gust crests glow while the rest of the field stays dark.

## Rolling Meadow

The hero preset: a strong crosswind from left to right, foreground blades almost horizontal at peak gusts, long bright streaks separated by dark gaps, gusts crossing the frame in about one to two seconds, and loose wisps whipping above the grass.

| Setting | Value |
| --- | --- |
| Direction | 0° (blows toward +X) |
| Base Lean | 0.6 |
| Gust Strength | 0.4 |
| Gust Scale | 0.2 (patches about 5 m across) |
| Gust Stretch | 3.3 |
| Gust Speed | 4 m/s |
| Max Bend | 80° |
| Stiffness | 1.6 |
| Flutter Strength | 0.08 |
| Flutter Frequency | 3 Hz |
| Wisp Flutter | 2x |
| Tip Lag | 0.15 s |
| Wind brightening (material) | 0.6 |

Use a camera looking along +Y so that the wind blows from left to right on screen.

## Animation types

Open the **Wind Type** menu in the **Wind** panel. Selecting a type fills the sliders. If you then change a slider, the type shows as **Custom**.

| Type | Look |
| --- | --- |
| **Rolling Meadow** | Strong crosswind, racing gust streaks, glowing crests |
| **Gentle Breeze** | Calm sway, small slow gusts, upright grass |
| **Storm** | Violent and turbulent, with the direction wandering by up to 30° |
| **Rolling Waves** | Regular parallel rows, a stylised or anime look. Adjust wavelength and speed |
| **Vortex** | Grass swirls around a point. Goes with a Vortex [effector](effectors.md) |
| **Radial Blast** | Grass is flattened outward. Goes with a Radial Blast effector |
| **Trample Path** | Grass parts around a moving object. Goes with a Trample effector |
| **Toon Bob** | Whole blades rock without bending. Cheap and stylised |

Vortex, Radial Blast and Trample Path are wind types that pair with an effector of the same kind. If the layer has none, Swayfield tells you to add one. The effectors themselves are separate objects (Vortex, Radial Blast, Trample and Shelter), and you can add any number of them on top of any wind type.

## Controls

- **Intensity** (0 to 2) scales all wind at once. Keyframe it for gusty shots.
- **Time Offset** and **Speed Multiplier** make layers move out of step.
- The **Direction Variation** sub-panel (**Direction Variation** and **Variation Speed**) lets the direction wander. Storm uses this.
- **Sway Mode**: Bend, or Rigid (whole blades rock).
- **Gust Evolution** and **Gust Contrast** change how fast the gust shapes change and how sharp the streaks are.

### Direction

**Direction** is an angle around the world's up axis. 0° blows toward +X. For animated direction, click **Add Direction Empty** and rotate the new empty around Z. Its local X axis sets the wind, so you can keyframe its rotation.

## Seamless loops for social media

To make a loop, for example 240 frames:

1. In the **Wind** panel, open the **Loop** sub-panel and turn on **Loop**.
2. Set **Loop Length** to 240.
3. Set your scene's frame range to 1 to 240.
4. Render.

Frame 241 would match frame 1, so the clip repeats with no jump. Loop mode works by blending the gust field between the current time and one loop earlier.

!!! tip
    A loop only covers the wind. Do not keyframe other things (like the camera) unless they loop too. If you keyframe Intensity, make the last key match the first.

## Freeze and Mute

- **Freeze Wind** (the **Freeze** toggle) holds the wind still at the current **Time Offset**. Use it to pose a still frame.
- **Mute in Viewport** turns wind off in the viewport only, for speed. Renders keep wind.

## Shelter

Paint a **Wind Strength** map to weaken wind behind walls or rocks. See [Painting and masks](painting-and-masks.md#other-maps).

## Distance savings

With **Animation LOD** on (the default), blades far from the camera rock as a whole instead of bending. You can set the start and end distance in the Performance panel.
