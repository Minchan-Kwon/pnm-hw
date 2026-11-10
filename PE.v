// Author: Minchan Kwon
// Parameterized Processing Element for PIM-enabled SSD
// Performs INT8 GEMV operations and 16-way element-wise multiplication
// Multiplication is performed in INT8 and accumulation is done in INT32
// Requantizes the INT32 accumulation into INT8

module PE #(
    parameter WAY = 16        // Number of parallel multipliers
    parameter PRECISION = 8   // INT8: 8, FP16/BF16: 16, INT32: 32
    parameter ACC_WIDTH = 32  // Accumulator width
)(
    input clk,
    input rstn,

    // Control signals
    input enable,
    input opcode,
    output done,
    input acc_clear,
    input acc_enable,

    // Data input
    input signed [PRECISION-1:0] weight [0:WAY-1],      // 16 INT8 weights
    input signed [PRECISION-1:0] activation [0:WAY-1],  // 16 INT8 activations

    // Quantization
    input [31:0] requant_mult,
    input [7:0] requant_shift,

    // Data output
    output reg [PRECISION-1:0] gemv_o,
    output reg [2*PRECISION-1:0] hadamard_o [0:WAY-1]  // 
);

// MAC & Element-wise product

// Requantization
    

endmodule