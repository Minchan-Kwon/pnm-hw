// Author: Minchan Kwon
// Parameterized Processing Element for PIM-enabled SSD
// Performs INT8 GEMV operations and 16-way element-wise multiplication
// Multiplication is performed in INT8 and accumulation is done in INT32
// Requantizes the INT32 accumulation into INT8

module PE #(
    parameter WAY = 16,        // Number of parallel multipliers
    parameter PRECISION = 8,   // INT8: 8, FP16/BF16: 16, INT32: 32
    parameter ACC_WIDTH = 32   // Accumulator width
)(
    input                        clk,
    input                        rstn,

    // Control signals
    input                        opcode,       // 0: GEMV, 1: Hadamard
    input                        acc_clear,
    input                        acc_enable,
    input                        requant_bypass, // Hadamard only. 1: output raw INT16 product, 0: requantized INT8

    // Data input
    input signed [PRECISION-1:0] weight [0:WAY-1],      // 16 INT8 weights
    input signed [PRECISION-1:0] activation [0:WAY-1],  // 16 INT8 activations

    // Quantization
    // FP16 requantization scale (= weight scale * input scale / output scale)
    input                 [15:0] requant_scale,

    // Data output
    output reg   [PRECISION-1:0] gemv_o,
    // Bypass: raw INT16 product / Requant: INT8 result sign-extended to 2*PRECISION bits
    output reg [2*PRECISION-1:0] hadamard_o [0:WAY-1]
);
    ////////////////////////////// Opcode //////////////////////////////
    localparam OP_GEMV     = 1'b0;
    localparam OP_HADAMARD = 1'b1;

    wire is_gemv     = (opcode == OP_GEMV);
    wire is_hadamard = (opcode == OP_HADAMARD);

    ////////////////////////////// Multipliers //////////////////////////////
    wire signed [2*PRECISION-1:0] product [0:WAY-1];

    genvar i;
    generate
        for (i = 0; i < WAY; i = i + 1) begin : multiplier_gen
            assign product[i] = weight[i] * activation[i];
        end
    endgenerate

    ////////////////////////////// Adder tree //////////////////////////////
    localparam DEPTH = $clog2(WAY);              // Adder tree depth
    localparam P = 1 << DEPTH;                   // WAY rounded up to PoT
    localparam INITIAL_WIDTH = 2*PRECISION + 1;  // Product width + 1 carry bit
    localparam SUM_WIDTH = 2*PRECISION + DEPTH;  // Product width + 1 carry bit per depth

    // tree[d][k]: k-th partial sum at depth d
    // Only the lower (2*PRECISION + d) bits are meaningful at depth d; upper bits are sign bits
    wire signed [SUM_WIDTH-1:0] tree [0:DEPTH][0:P-1];
    wire signed [SUM_WIDTH-1:0] sum = tree[DEPTH][0];

    genvar j;
    generate
        // Depth 0: Connect the product values to the adder tree
        for (i = 0; i < P; i = i + 1) begin : wire_gen
            assign tree[0][i] = is_gemv ? product[i] : {SUM_WIDTH{1'b0}};  // Hold adder tree at 0 during Hadamard
        end

        // Depth >= 1: Adder tree, adder width grows by 1 at each depth
        for (i = 0; i < DEPTH; i = i + 1) begin : depth_gen
            localparam OUT_WIDTH = INITIAL_WIDTH + i;  // Adder output width at this depth
            localparam IN_WIDTH  = OUT_WIDTH - 1;      // Meaningful bits of each operand

            for (j = 0; j < (P >> (i+1)); j = j + 1) begin : adder_gen
                wire signed [OUT_WIDTH-1:0] s = $signed(tree[i][2*j  ][IN_WIDTH-1:0])
                                              + $signed(tree[i][2*j+1][IN_WIDTH-1:0]);
                assign tree[i+1][j] = s;  // Sign-extended to SUM_WIDTH
            end
        end
    endgenerate


    ////////////////////////////// Accumulator //////////////////////////////
    reg  signed [ACC_WIDTH-1:0] acc;
    wire signed [ACC_WIDTH-1:0] acc_prev;

    assign acc_prev = acc_clear ? {ACC_WIDTH{1'b0}} : acc;  // Accumulator clear

    always @(posedge clk or negedge rstn) begin
        if (!rstn) begin
            acc <= 0;
        end
        else if (acc_enable && is_gemv) begin  // Accumulate only in GEMV
            acc <= acc_prev + sum;
        end
    end

    ////////////////////////////// Requantize //////////////////////////////
    // GEMV: 1 unit on the INT32 accumulation
    wire signed [PRECISION-1:0] gemv_requant;

    requant #(
        .IN_WIDTH  (ACC_WIDTH),
        .OUT_WIDTH (PRECISION)
    ) gemv_requant_unit (
        .in    (acc),
        .scale (requant_scale),
        .out   (gemv_requant)
    );

    // Hadamard: WAY units, one per INT16 product
    wire signed [PRECISION-1:0] hadamard_requant [0:WAY-1];

    generate
        for (i = 0; i < WAY; i = i + 1) begin : hadamard_requant_gen
            requant #(
                .IN_WIDTH  (2*PRECISION),
                .OUT_WIDTH (PRECISION)
            ) hadamard_requant_unit (
                .in    (is_hadamard ? product[i] : {2*PRECISION{1'b0}}),  // Hold at 0 during GEMV
                .scale (requant_scale),
                .out   (hadamard_requant[i])
            );
        end
    endgenerate

    // Assign output
    always @(*) begin
        gemv_o = gemv_requant;
    end

    generate
        for (i = 0; i < WAY; i = i + 1) begin : h_out_gen
            always @(*) begin
                if (requant_bypass)
                    hadamard_o[i] = product[i];  // Raw INT16 product
                else
                    hadamard_o[i] = {{PRECISION{hadamard_requant[i][PRECISION-1]}}, hadamard_requant[i]};  // Sign-extended INT8
            end
        end
    endgenerate

endmodule