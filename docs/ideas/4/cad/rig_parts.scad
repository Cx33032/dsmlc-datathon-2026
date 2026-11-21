// Idea 4 tabletop "well" rig - editable OpenSCAD version of the parts in this folder.
// The ready-to-print STL files were made by data/ideas/4/cad/make_parts.py with the same numbers.
// Use this file only if you want to change a size. Free program: https://openscad.org
//
// How to use:
//   1. Measure your motor, servo, rod and jar with calipers. Change the numbers below.
//   2. Set PART to the part you want. Press F6 (render), then File > Export > STL.
//
// All sizes are in millimetres.

PART = "wellhead_plate";  // wellhead_plate | drive_head | coupling_motor_side | coupling_rod_side | brake_drum
                        // brake_pad | paddle_rotor | pcp_rotor | pcp_stator_cutaway

rod_d        = 4.0;   // wooden dowel or steel rod ("rod string")
rod_clear    = 0.6;   // extra diameter where the rod must turn freely
rod_press    = 0.2;   // extra diameter where the rod is glued or pressed in
jar_inner_d  = 58.0;  // inside diameter of the jar mouth ("wellbore")
lid_d        = 90.0;  // lid diameter, must be wider than the jar rim
motor_w      = 20.4;  // DC motor can, long flat-to-flat
motor_t      = 15.2;  // DC motor can, short flat-to-flat
motor_boss_d = 6.6;   // round boss around the motor shaft
motor_shaft_d= 2.0;
servo_l      = 22.8;  // SG90 body length
servo_w      = 12.4;  // SG90 body width
magnet_d     = 6.0;   // optional 6 x 3 mm disc magnets
magnet_t     = 3.0;
pcp_r        = 6.0;   // PCP rotor section radius
pcp_e        = 2.0;   // PCP eccentricity
pcp_pitch    = 40.0;  // rotor pitch; stator pitch is 2 x this
pcp_len      = 120.0;
pcp_clear    = 0.45;

$fn = 96;
rc = (rod_d + rod_clear) / 2;
rp = (rod_d + rod_press) / 2;

module tube(ri, ro, h) { difference() { cylinder(r = ro, h = h); translate([0, 0, -1]) cylinder(r = ri, h = h + 2); } }

servo_y  = -31;   // servo cradle centre; move closer (e.g. -28) if the horn + pad cannot reach the drum
pillar_h = 69;    // keeps the coupling above the servo horn / brake drum

// Print flat side down, then flip: the lip and boss go down into the jar mouth. No supports.
module wellhead_plate() {
    tube(rc, lid_d / 2, 4);                                                // plate with rod hole
    translate([0, 0, 3.5]) tube(jar_inner_d / 2 - 2.5, jar_inner_d / 2 - 0.4, 6.5); // centring lip
    translate([0, 0, 3.5]) tube(rc, 7, 10.5);                              // guide boss ("stuffing box")
}

// Glue or screw onto the plate. Pillars carry the motor; the cradle holds the SG90 standing shaft-up.
module drive_head() {
    for (x = [-20, 20]) translate([x - 7, -7, 0]) cube([14, 14, 3]);      // pillar feet
    translate([-27, -11, 0]) cube([54, 3, 3]);                             // cross bar (clear of the rod)
    translate([-6, servo_y + servo_w / 2, 0]) cube([12, -8 - (servo_y + servo_w / 2), 3]); // spine
    translate([-servo_l / 2 - 2, servo_y - servo_w / 2 - 2, 0]) cube([servo_l + 4, servo_w + 4, 3]); // cradle floor
    for (x = [-20, 20]) translate([x - 4, -5, 0]) cube([8, 10, pillar_h]); // pillars
    translate([0, 0, pillar_h - 4]) difference() {                         // bridge with motor-boss hole
        translate([-24, -9, 0]) cube([48, 18, 4]);
        translate([0, 0, -1]) cylinder(r = motor_boss_d / 2, h = 6);
    }
    translate([0, 0, pillar_h - 0.5]) difference() {                       // motor pocket
        translate([-motor_w / 2 - 2, -motor_t / 2 - 2, 0]) cube([motor_w + 4, motor_t + 4, 12.5]);
        translate([-motor_w / 2, -motor_t / 2, -1]) cube([motor_w, motor_t, 15]);
    }
    translate([0, servo_y, 2.5]) difference() {                            // servo cradle walls
        translate([-servo_l / 2 - 2, -servo_w / 2 - 2, 0]) cube([servo_l + 4, servo_w + 4, 16]);
        translate([-servo_l / 2, -servo_w / 2, -1]) cube([servo_l, servo_w, 20]);
    }
}

// Printed face-up (dogs up, no supports). In use the motor-side half is turned over.
module coupling(motor_side) {
    bore_r = motor_side ? (motor_shaft_d - 0.1) / 2 : rp;
    difference() {
        cylinder(r = 8, h = 10);
        translate([0, 0, -1]) cylinder(r = bore_r, h = 7);                   // shaft / rod bore from the bottom
        translate([0, 0, 10 - magnet_t - 0.2]) cylinder(r = (magnet_d + 0.3) / 2, h = magnet_t + 1); // magnet pocket
    }
    for (k = [0 : 2]) rotate([0, 0, (motor_side ? 0 : 60) + 120 * k])     // three dogs on the face
        translate([3.8, -1.9, 9.8]) cube([4.2, 3.8, 3.2]);
}

module brake_drum() { tube(rp, 12, 6); }

module brake_pad() { translate([-5, 0, 0]) cube([10, 4, 7]); translate([-2, -6, 0]) cube([4, 6.5, 3]); }

module paddle_rotor() {
    difference() { cylinder(r = 5.5, h = 16); translate([0, 0, 4]) cylinder(r = rp, h = 13); }
    for (k = [0 : 3]) rotate([0, 0, 90 * k]) translate([4.5, -0.9, 0]) cube([16.5, 1.8, 13]);
}

module pcp_rotor() {
    difference() {
        linear_extrude(height = pcp_len, twist = -360 * pcp_len / pcp_pitch, slices = pcp_len * 2)
            translate([pcp_e, 0]) circle(r = pcp_r);
        translate([0, 0, pcp_len - 10]) cylinder(r = rp, h = 11);         // socket for the rod
    }
}

module pcp_stator_cutaway(R = 14, window = 90) {
    difference() {
        cylinder(r = R, h = pcp_len);
        translate([0, 0, -1])
            linear_extrude(height = pcp_len + 2, twist = -360 * (pcp_len + 2) / (2 * pcp_pitch), slices = pcp_len * 2)
                hull() for (x = [-2 * pcp_e, 2 * pcp_e]) translate([x, 0]) circle(r = pcp_r + pcp_clear);
        // open window so you can see the cavities
        translate([0, 0, -1]) linear_extrude(pcp_len + 2)
            polygon([[0, 0], [2 * R * cos(window / 2), 2 * R * sin(window / 2)], [2 * R, 0],
                     [2 * R * cos(-window / 2), 2 * R * sin(-window / 2)]]);
    }
}

if (PART == "wellhead_plate") wellhead_plate();
if (PART == "drive_head") drive_head();
if (PART == "coupling_motor_side") coupling(true);
if (PART == "coupling_rod_side") coupling(false);
if (PART == "brake_drum") brake_drum();
if (PART == "brake_pad") brake_pad();
if (PART == "paddle_rotor") paddle_rotor();
if (PART == "pcp_rotor") pcp_rotor();
if (PART == "pcp_stator_cutaway") pcp_stator_cutaway();
