// AUTO-GENERATED -- do not edit by hand
// config: XFB=8 NSEG=32 OW=None HTANFB=11 GB=3 fit=search
// model vs golden (active band): max 1 LSB, 46583 / 3407872 mismatches

localparam integer XFB    = 8;      // |x| fraction bits
localparam integer XW     = 11;     // |x| width (3 integer bits + XFB)
localparam integer XMAX   = 2048;   // 8.0 in |x| format; at or above -> htan = 0.5
localparam integer NSEG   = 32;     // number of segments over [0, 8)
localparam integer SEGB   = 5;      // segment index bits
localparam integer SEGLSB = 6;      // segment index starts at this bit of |x|
localparam integer DROP   = 0;      // low offset bits dropped before the multiply
localparam integer OFFW   = 6;      // offset width into the multiplier
localparam integer HTANFB = 11;     // htan fraction bits
localparam integer GB     = 3;      // guard bits on slope/intercept, shifted out at the end
localparam integer SLOPEW = 6;      // signed width of slope
localparam integer ICPTW  = 14;     // signed width of intercept
localparam integer HTANW  = 12;     // signed width of htan

// constant coefficient table: returns {slope, intercept}
function [SLOPEW+ICPTW-1:0] htan_coef;
    input [SEGB-1:0] seg;
    begin
        case (seg)
            5'd0  : htan_coef = {6'h10, 14'h0001};   // slope =     16, intercept =        1
            5'd1  : htan_coef = {6'h0f, 14'h040d};   // slope =     15, intercept =     1037
            5'd2  : htan_coef = {6'h0f, 14'h07d4};   // slope =     15, intercept =     2004
            5'd3  : htan_coef = {6'h0d, 14'h0b8d};   // slope =     13, intercept =     2957
            5'd4  : htan_coef = {6'h0c, 14'h0ed1};   // slope =     12, intercept =     3793
            5'd5  : htan_coef = {6'h0a, 14'h11d7};   // slope =     10, intercept =     4567
            5'd6  : htan_coef = {6'h09, 14'h1459};   // slope =      9, intercept =     5209
            5'd7  : htan_coef = {6'h07, 14'h169e};   // slope =      7, intercept =     5790
            5'd8  : htan_coef = {6'h06, 14'h186e};   // slope =      6, intercept =     6254
            5'd9  : htan_coef = {6'h05, 14'h19ee};   // slope =      5, intercept =     6638
            5'd10 : htan_coef = {6'h04, 14'h1b2d};   // slope =      4, intercept =     6957
            5'd11 : htan_coef = {6'h03, 14'h1c38};   // slope =      3, intercept =     7224
            5'd12 : htan_coef = {6'h03, 14'h1cf1};   // slope =      3, intercept =     7409
            5'd13 : htan_coef = {6'h02, 14'h1da2};   // slope =      2, intercept =     7586
            5'd14 : htan_coef = {6'h02, 14'h1e1d};   // slope =      2, intercept =     7709
            5'd15 : htan_coef = {6'h01, 14'h1e95};   // slope =      1, intercept =     7829
            5'd16 : htan_coef = {6'h01, 14'h1edc};   // slope =      1, intercept =     7900
            5'd17 : htan_coef = {6'h01, 14'h1f18};   // slope =      1, intercept =     7960
            5'd18 : htan_coef = {6'h01, 14'h1f43};   // slope =      1, intercept =     8003
            5'd19 : htan_coef = {6'h00, 14'h1f80};   // slope =      0, intercept =     8064
            5'd20 : htan_coef = {6'h00, 14'h1fa1};   // slope =      0, intercept =     8097
            5'd21 : htan_coef = {6'h00, 14'h1fb9};   // slope =      0, intercept =     8121
            5'd22 : htan_coef = {6'h00, 14'h1fc0};   // slope =      0, intercept =     8128
            5'd23 : htan_coef = {6'h00, 14'h1fcc};   // slope =      0, intercept =     8140
            5'd24 : htan_coef = {6'h00, 14'h1fd8};   // slope =      0, intercept =     8152
            5'd25 : htan_coef = {6'h00, 14'h1fe1};   // slope =      0, intercept =     8161
            5'd26 : htan_coef = {6'h00, 14'h1fe7};   // slope =      0, intercept =     8167
            5'd27 : htan_coef = {6'h00, 14'h1fed};   // slope =      0, intercept =     8173
            5'd28 : htan_coef = {6'h00, 14'h1ff1};   // slope =      0, intercept =     8177
            5'd29 : htan_coef = {6'h00, 14'h1ff4};   // slope =      0, intercept =     8180
            5'd30 : htan_coef = {6'h00, 14'h1ff7};   // slope =      0, intercept =     8183
            5'd31 : htan_coef = {6'h00, 14'h1ff9};   // slope =      0, intercept =     8185
            default: htan_coef = {(SLOPEW+ICPTW){1'b0}};
        endcase
    end
endfunction
