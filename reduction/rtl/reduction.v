// Author: Minchan Kwon
// Reduction unit for the SSD controller
// Adds the down-projection partial sums that arrive from different dies.
//
// Every die requantizes its partial sum with the same scale
// (per-tensor weight scale * static input scale / static output scale),
// so the reduction is plain integer addition with no rescaling.
//
// Data movement
//   - LANES elements arrive per beat (one beat per clock when in_valid = 1).
//   - DEPTH is the window size, not the hidden size: the controller splits an output
//     vector of any length into windows of DEPTH beats, and each die sends up to
//     DEPTH beats of a window before the next die takes over. Rows are reused for
//     every window, so any model's hidden size works without a hardware change.
//     in_addr = beat position inside the current window (0..DEPTH-1); within a
//     window, partial sums may arrive in any order and interleave freely.
//   - A hidden size that is not a multiple of LANES: pad the last beat with zeros.
//   - The controller marks the first and last partial sum of each beat:
//       in_first = 1 : overwrite the accumulator (start a new sum)
//       in_last  = 1 : the sum is complete, send it out on the next clock
//     A single-term sum has both flags set.
//   - DEPTH = 1 degenerates to one row of adders + registers (in_addr tied to 0).
//
// Precision
//   - Accumulator is IN_WIDTH + clog2(MAX_TERMS) bits, so adding up to MAX_TERMS
//     partial sums can never overflow.
//   - If OUT_WIDTH < ACC_WIDTH the result is clamped symmetrically to
//     [-(2^(OUT_WIDTH-1)-1), +(2^(OUT_WIDTH-1)-1)], matching requant.v.
//
// Timing: one adder per lane (ACC_WIDTH bits) + a DEPTH:1 read mux, one cycle latency.

module reduction #(
    parameter LANES      = 64,                            // Elements per beat
    parameter IN_WIDTH   = 8,                             // Partial-sum width (INT8)
    parameter MAX_TERMS  = 16,                            // Max partial sums added per element
    parameter DEPTH      = 32,                            // Accumulator rows = beats per window (not hidden size)
    parameter ACC_WIDTH  = IN_WIDTH + $clog2(MAX_TERMS),  // Overflow-free accumulator width
    parameter OUT_WIDTH  = ACC_WIDTH,                     // Output width (< ACC_WIDTH -> saturate)
    parameter ADDR_WIDTH = (DEPTH > 1) ? $clog2(DEPTH) : 1
)(
    input                             clk,
    input                             rstn,

    // Partial-sum input
    input                             in_valid,
    input                             in_first,  // First partial sum for this beat: overwrite
    input                             in_last,   // Last partial sum for this beat: emit result
    input      [ADDR_WIDTH-1:0]       in_addr,   // Beat index within the output vector
    input      [LANES*IN_WIDTH-1:0]   in_data,   // Lane l = in_data[l*IN_WIDTH +: IN_WIDTH], signed

    // Reduced output (valid one clock after the in_last beat)
    output reg                        out_valid,
    output reg [ADDR_WIDTH-1:0]       out_addr,
    output reg [LANES*OUT_WIDTH-1:0]  out_data   // Lane l = out_data[l*OUT_WIDTH +: OUT_WIDTH], signed
);
    // Accumulator rows: no reset needed, in_first overwrites
    reg  [LANES*ACC_WIDTH-1:0] acc [0:DEPTH-1];
    wire [LANES*ACC_WIDTH-1:0] acc_row = acc[in_addr];

    wire [LANES*ACC_WIDTH-1:0] sum;  // New accumulator value, all lanes
    wire [LANES*OUT_WIDTH-1:0] res;  // Output-width result, all lanes

    genvar l;
    generate
        for (l = 0; l < LANES; l = l + 1) begin : lane
            wire signed [IN_WIDTH-1:0]  x     = in_data[l*IN_WIDTH +: IN_WIDTH];
            wire signed [ACC_WIDTH-1:0] x_ext = x;  // Sign extension
            wire signed [ACC_WIDTH-1:0] old   = acc_row[l*ACC_WIDTH +: ACC_WIDTH];
            wire signed [ACC_WIDTH-1:0] s     = in_first ? x_ext : (old + x_ext);

            assign sum[l*ACC_WIDTH +: ACC_WIDTH] = s;

            if (OUT_WIDTH < ACC_WIDTH) begin : clamp
                localparam signed [ACC_WIDTH-1:0] MAX = (1 << (OUT_WIDTH-1)) - 1;
                localparam signed [ACC_WIDTH-1:0] MIN = -MAX;
                wire signed [ACC_WIDTH-1:0] c = (s > MAX) ? MAX : (s < MIN) ? MIN : s;
                assign res[l*OUT_WIDTH +: OUT_WIDTH] = c[OUT_WIDTH-1:0];
            end else begin : extend
                wire signed [OUT_WIDTH-1:0] e = s;  // Sign extension (or same width)
                assign res[l*OUT_WIDTH +: OUT_WIDTH] = e;
            end
        end
    endgenerate

    // Accumulate (read-modify-write in one cycle)
    always @(posedge clk) begin
        if (in_valid) acc[in_addr] <= sum;
    end

    // Output register
    always @(posedge clk or negedge rstn) begin
        if (!rstn) out_valid <= 1'b0;
        else       out_valid <= in_valid & in_last;
    end

    always @(posedge clk) begin
        if (in_valid & in_last) begin
            out_addr <= in_addr;
            out_data <= res;
        end
    end

endmodule
